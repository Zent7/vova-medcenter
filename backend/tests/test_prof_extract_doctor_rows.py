from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

import xlrd


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.document_generator import (  # noqa: E402
    PROF_AMB_EXAM_BLOCKS,
    PROF_EXTRACT_CLEARED_DOCTOR_ROWS,
    PROF_EXTRACT_DOCTOR_ROWS,
    _generate_prof_amb_xls,
    _prof_amb_exam_block_values,
    _prof_extract_doctor_row_values,
)


def exam(role_id, doctor_name, *, is_completed=True, completed_at=None, conclusion="Годен"):
    return SimpleNamespace(
        doctor_role_id=role_id,
        doctor_name=doctor_name,
        result_text="",
        diagnosis="",
        fields_json={"conclusion": conclusion},
        is_completed=is_completed,
        completed_at=completed_at,
    )


class ProfExtractDoctorRowsTests(unittest.TestCase):
    def test_completed_therapist_fills_therapist_row(self):
        encounter = SimpleNamespace(encounter_date=date(2026, 6, 24))
        rows = _prof_extract_doctor_row_values(
            {"therapist": exam("therapist", "Казаков И.В.", completed_at=datetime(2026, 6, 23, 9, 30))},
            encounter,
        )

        self.assertEqual(rows[0], (32, "Терапевт Казаков И.В.", date(2026, 6, 23), "годен"))

    def test_uncompleted_or_missing_roles_are_empty(self):
        encounter = SimpleNamespace(encounter_date=date(2026, 6, 24))
        rows = _prof_extract_doctor_row_values(
            {"therapist": exam("therapist", "Казаков И.В.", is_completed=False)},
            encounter,
        )

        self.assertEqual(rows[0], (32, "", "", ""))
        gynecologist_row = rows[[role for role, _, _ in PROF_EXTRACT_DOCTOR_ROWS].index("gynecologist")]
        self.assertEqual(gynecologist_row, (45, "", "", ""))

    def test_psychiatrist_narcologist_is_not_exported(self):
        encounter = SimpleNamespace(encounter_date=date(2026, 6, 24))
        rows = _prof_extract_doctor_row_values(
            {
                "psychiatrist": exam("psychiatrist", "Аносов И.Е."),
                "psychiatrist-narcologist": exam("psychiatrist-narcologist", "Аносов И.Е."),
            },
            encounter,
        )

        self.assertEqual(rows[1], (34, "Психиатр Аносов И.Е.", date(2026, 6, 24), "годен"))
        self.assertNotIn(37, [row[0] for row in rows])
        self.assertEqual(PROF_EXTRACT_CLEARED_DOCTOR_ROWS, (37,))

    def test_rows_keep_template_order(self):
        rows = _prof_extract_doctor_row_values({}, None)

        self.assertEqual(
            [(role_id, row_index) for role_id, _, row_index in PROF_EXTRACT_DOCTOR_ROWS],
            [
                ("therapist", 32),
                ("psychiatrist", 34),
                ("neurologist", 39),
                ("otolaryngologist", 41),
                ("surgeon", 43),
                ("gynecologist", 45),
                ("ophthalmologist", 48),
                ("dermatologist", 50),
                ("dentist", 52),
            ],
        )
        self.assertEqual([row[0] for row in rows], [row_index for _, _, row_index in PROF_EXTRACT_DOCTOR_ROWS])

    def test_amb_blocks_include_only_completed_selected_doctors_without_gaps(self):
        encounter = SimpleNamespace(encounter_date=date(2026, 6, 24))
        blocks = _prof_amb_exam_block_values(
            {
                "therapist": exam("therapist", "Казаков И.В.", completed_at=datetime(2026, 6, 23, 9, 30)),
                "surgeon": exam("surgeon", "Конюк М.В."),
                "dentist": exam("dentist", "Шадрикова Ю.А."),
                "gynecologist": exam("gynecologist", "Барсуков А.Ф.", is_completed=False),
            },
            encounter,
        )

        self.assertEqual([role_id for role_id, _ in blocks], ["therapist", "surgeon", "dentist"])
        self.assertEqual(blocks[0][1]["title"], "Врач терапевт")
        self.assertEqual(blocks[0][1]["date"], date(2026, 6, 23))
        self.assertEqual(blocks[1][1]["title"], "Врач хирург")
        self.assertEqual(blocks[1][1]["date"], date(2026, 6, 24))
        self.assertEqual(blocks[2][1]["doctor"], "Шадрикова Ю.А.")

    def test_amb_template_has_room_for_every_prof_extract_role(self):
        self.assertGreaterEqual(len(PROF_AMB_EXAM_BLOCKS), len(PROF_EXTRACT_DOCTOR_ROWS))

    def test_generated_amb_sheet_writes_every_selected_doctor_block(self):
        template_path = next(
            path
            for path in (Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates").glob("*.xls")
            if path.name.startswith("Выписка")
        )
        output_path = Path(tempfile.gettempdir()) / "prof_extract_doctor_rows_test.xls"
        roles = [
            ("therapist", "Казаков И.В."),
            ("psychiatrist", "Аносов И.Е."),
            ("neurologist", "Сибирцев В.А."),
            ("otolaryngologist", "Изория С.Г."),
            ("surgeon", "Конюк М.В."),
            ("gynecologist", "Барсуков А.Ф."),
            ("ophthalmologist", "Дадалина Т.В."),
            ("dermatologist", "Мехдиева Н.Ш.К."),
            ("dentist", "Шадрикова Ю.А."),
        ]
        exams = [
            exam(role_id, doctor_name, completed_at=datetime(2026, 6, 24, 9, 30))
            for role_id, doctor_name in roles
        ]
        client = SimpleNamespace(
            birth_date=date(1990, 1, 2),
            document_type="Паспорт РФ",
            admission_category="",
            legacy_payload_json={},
        )
        encounter = SimpleNamespace(encounter_date=date(2026, 6, 24))
        context = {
            "ReferenceNumber": "123",
            "ClientCalc": "Тестов Тест Тестович",
            "SexCalc": "мужской",
            "SubjectCalc": "Санкт-Петербург",
            "DistrictCalc": "",
            "CityCalc": "Санкт-Петербург",
            "StreetCalc": "Невский 1",
            "AddressCalc": "Санкт-Петербург, Невский 1",
            "Phone": "",
            "SNILS": "",
            "DocumentSeries": "1234",
            "DocumentNumber": "567890",
            "CompanyName": "ООО Тест",
            "Post": "Пекарь",
            "Conclusion": "Годен",
            "BirthDateCalc_DAY": "02",
            "BirthDateCalc_DATEMONTH": "января",
            "BirthDateCalc_YEAR": "1990",
            "VisitDate_DATEMONTH": "июня",
        }

        _generate_prof_amb_xls(template_path, output_path, context, client, encounter, exams)

        book = xlrd.open_workbook(file_contents=output_path.read_bytes(), formatting_info=True)
        amb_sheet = book.sheet_by_index(1)
        title_cells = [block["title_cell"] for block in PROF_AMB_EXAM_BLOCKS[: len(roles)]]
        self.assertEqual(
            [amb_sheet.cell_value(row_index, col_index) for row_index, col_index in title_cells],
            [
                "Врач терапевт",
                "Врач психиатр",
                "Врач невролог",
                "Врач отоларинголог",
                "Врач хирург",
                "Врач гинеколог",
                "Врач офтальмолог",
                "Врач дерматовенеролог",
                "Врач стоматолог",
            ],
        )


if __name__ == "__main__":
    unittest.main()
