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
    PROF_EXTRACT_DATE_COL,
    PROF_EXTRACT_DOCTOR_COL,
    PROF_EXTRACT_DOCTOR_ROWS,
    PROF_EXTRACT_SEQUENCE_COL,
    _generate_prof_amb_xls,
    _prof_amb_exam_block_values,
    _prof_extract_doctor_row_values,
    _xls_auto_marker_values,
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
    def _prof_template_path(self) -> Path:
        return next(
            path
            for path in (Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates").glob("*.xls")
            if path.name.startswith("Выписка")
        )

    def _client(self):
        return SimpleNamespace(
            birth_date=date(1990, 1, 2),
            document_type="Паспорт РФ",
            admission_category="",
            legacy_payload_json={},
        )

    def _context(self) -> dict[str, str]:
        return {
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

    def test_completed_therapist_fills_therapist_row(self):
        encounter = SimpleNamespace(encounter_date=date(2026, 6, 24))
        rows = _prof_extract_doctor_row_values(
            {"therapist": exam("therapist", "Казаков И.В.", completed_at=datetime(2026, 6, 23, 9, 30))},
            encounter,
        )

        self.assertEqual(rows[0], (32, "Терапевт Казаков И.В.", date(2026, 6, 23), "годен"))

    def test_uncompleted_or_missing_roles_are_skipped(self):
        encounter = SimpleNamespace(encounter_date=date(2026, 6, 24))
        rows = _prof_extract_doctor_row_values(
            {"therapist": exam("therapist", "Казаков И.В.", is_completed=False)},
            encounter,
        )

        self.assertEqual(rows, [])

    def test_psychiatrist_narcologist_is_exported_as_separate_row(self):
        encounter = SimpleNamespace(encounter_date=date(2026, 6, 24))
        rows = _prof_extract_doctor_row_values(
            {
                "psychiatrist": exam("psychiatrist", "Аносов И.Е."),
                "psychiatrist-narcologist": exam("psychiatrist-narcologist", "Аносов И.Е."),
            },
            encounter,
        )

        self.assertEqual(rows[0], (32, "Психиатр Аносов И.Е.", date(2026, 6, 24), "годен"))
        self.assertEqual(rows[1], (34, "Психиатр-нарколог Аносов И.Е.", date(2026, 6, 24), "годен"))
        self.assertEqual(PROF_EXTRACT_CLEARED_DOCTOR_ROWS, ())

    def test_rows_keep_template_order(self):
        rows = _prof_extract_doctor_row_values({}, None)

        self.assertEqual(
            [(role_id, row_index) for role_id, _, row_index in PROF_EXTRACT_DOCTOR_ROWS],
            [
                ("therapist", 32),
                ("psychiatrist", 34),
                ("psychiatrist-narcologist", 37),
                ("neurologist", 39),
                ("otolaryngologist", 41),
                ("surgeon", 43),
                ("gynecologist", 45),
                ("ophthalmologist", 48),
                ("dermatologist", 50),
                ("dentist", 52),
            ],
        )
        self.assertEqual(rows, [])

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

    def test_client_doctor_names_override_generic_exam_doctor_names(self):
        encounter = SimpleNamespace(encounter_date=date(2026, 6, 24))
        client = SimpleNamespace(
            doctor_therapist="Казаков И.В.",
            doctor_psychiatrist="Аносов И.Е.",
            doctor_neurologist="Сибирцев В.А.",
            doctor_otolaryngologist="Изория С.Г.",
            doctor_surgeon="Конюк М.В.",
            doctor_gynecologist="Барсуков А.Ф.",
            doctor_ophthalmologist="Дадалина Т.В.",
            doctor_dermatologist="Мехдиева Н.Ш.К.",
            doctor_stomatologist="Шадрикова Ю.А.",
        )
        rows = _prof_extract_doctor_row_values(
            {
                "psychiatrist-narcologist": exam("psychiatrist-narcologist", "Сибирцев В.А."),
                "neurologist": exam("neurologist", "Сибирцев В.А."),
            },
            encounter,
            client,
        )
        blocks = _prof_amb_exam_block_values(
            {
                "psychiatrist-narcologist": exam("psychiatrist-narcologist", "Сибирцев В.А."),
                "neurologist": exam("neurologist", "Сибирцев В.А."),
            },
            encounter,
            client,
        )

        self.assertEqual(rows[0][1], "Психиатр-нарколог Аносов И.Е.")
        self.assertEqual(rows[1][1], "Невролог Сибирцев В.А.")
        self.assertEqual(blocks[0][1]["doctor"], "Аносов И.Е.")
        self.assertEqual(blocks[1][1]["doctor"], "Сибирцев В.А.")

    def test_auto_marker_values_use_client_doctor_names_by_role(self):
        encounter = SimpleNamespace(encounter_date=date(2026, 6, 24))
        client = SimpleNamespace(
            birth_date=date(1990, 1, 2),
            doctor_therapist="Казаков И.В.",
            doctor_psychiatrist="Аносов И.Е.",
            doctor_neurologist="Невролог Н.Н.",
            doctor_otolaryngologist="ЛОР Л.Л.",
            doctor_surgeon="Хирург Х.Х.",
            doctor_gynecologist="Гинеколог Г.Г.",
            doctor_ophthalmologist="Офтальмолог О.О.",
            doctor_dermatologist="Дерматолог Д.Д.",
            doctor_stomatologist="Стоматолог С.С.",
        )
        exams_by_role = {
            "psychiatrist": exam("psychiatrist", "Сибирцев В.А."),
            "psychiatrist-narcologist": exam("psychiatrist-narcologist", "Сибирцев В.А."),
            "neurologist": exam("neurologist", "Сибирцев В.А."),
        }

        values = _xls_auto_marker_values(self._context(), client, encounter, exams_by_role)
        marker_values = {aliases[0]: value for aliases, value in values}

        self.assertIn("Аносов И.Е.", marker_values["психиатр"])
        self.assertIn("Аносов И.Е.", marker_values["психиатр нарколог"])
        self.assertIn("Невролог Н.Н.", marker_values["невролог"])
        self.assertNotIn("Сибирцев В.А.", marker_values["психиатр"])
        self.assertNotIn("Сибирцев В.А.", marker_values["психиатр нарколог"])

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
            ("psychiatrist-narcologist", "Аносов И.Е."),
            ("neurologist", "Сибирцев В.А."),
            ("otolaryngologist", "Изория С.Г."),
            ("surgeon", "Конюк М.В."),
            ("gynecologist", "Барсуков А.Ф."),
            ("ophthalmologist", "Дадалина Т.В."),
            ("dermatologist", "Сит Мехдиева Н.Ш.К."),
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
                "Врач психиатр-нарколог",
                "Врач невролог",
                "Врач отоларинголог",
                "Врач хирург",
                "Врач гинеколог",
                "Врач офтальмолог",
                "Врач дерматовенеролог",
                "Врач стоматолог",
            ],
        )
        dermatologist_index = [role_id for role_id, _ in roles].index("dermatologist")
        doctor_row, doctor_col = PROF_AMB_EXAM_BLOCKS[dermatologist_index]["doctor_cell"]
        self.assertEqual(amb_sheet.cell_value(doctor_row, doctor_col), "Сит Мехдиева Н.Ш.К.")
        doctor_xf = book.xf_list[amb_sheet.cell_xf_index(doctor_row, doctor_col)]
        self.assertEqual(doctor_xf.alignment.shrink_to_fit, 0)
        self.assertIn((doctor_row, doctor_row + 1, doctor_col, 32), amb_sheet.merged_cells)
        date_row, date_col = PROF_AMB_EXAM_BLOCKS[dermatologist_index]["date_cell"]
        self.assertEqual(amb_sheet.cell_value(date_row, date_col), "24.06.26")
        pz2_sheet = book.sheet_by_name("ПЗ2")
        pz2_doctor_row = PROF_EXTRACT_DOCTOR_ROWS[dermatologist_index][2]
        self.assertEqual(
            pz2_sheet.cell_value(pz2_doctor_row, PROF_EXTRACT_DOCTOR_COL),
            "Дерматовенеролог Сит Мехдиева Н.Ш.К.",
        )
        self.assertEqual(pz2_sheet.cell_value(pz2_doctor_row, PROF_EXTRACT_DATE_COL), "24.06.26")
        pz2_doctor_xf = book.xf_list[pz2_sheet.cell_xf_index(pz2_doctor_row, PROF_EXTRACT_DOCTOR_COL)]
        self.assertEqual(pz2_doctor_xf.alignment.shrink_to_fit, 1)

    def test_generated_amb_sheet_hides_unused_blocks_and_compacts_pz2_rows(self):
        output_path = Path(tempfile.gettempdir()) / "prof_extract_doctor_rows_compact_test.xls"
        encounter = SimpleNamespace(encounter_date=date(2026, 6, 24))
        exams = [
            exam("therapist", "Казаков И.В.", completed_at=datetime(2026, 6, 24, 9, 30)),
            exam("surgeon", "Конюк М.В.", completed_at=datetime(2026, 6, 24, 9, 30)),
            exam("dentist", "Шадрикова Ю.А.", completed_at=datetime(2026, 6, 24, 9, 30)),
            exam("gynecologist", "Барсуков А.Ф.", is_completed=False),
        ]

        _generate_prof_amb_xls(self._prof_template_path(), output_path, self._context(), self._client(), encounter, exams)

        book = xlrd.open_workbook(file_contents=output_path.read_bytes(), formatting_info=True)
        amb_sheet = book.sheet_by_index(1)
        self.assertEqual(
            [amb_sheet.cell_value(*PROF_AMB_EXAM_BLOCKS[index]["title_cell"]) for index in range(3)],
            ["Врач терапевт", "Врач хирург", "Врач стоматолог"],
        )
        first_unused_block = PROF_AMB_EXAM_BLOCKS[3]
        unused_label_col = first_unused_block["title_cell"][1] - 9
        self.assertEqual(amb_sheet.cell_value(first_unused_block["date_cell"][0], unused_label_col), "")
        self.assertEqual(amb_sheet.cell_value(*first_unused_block["title_cell"]), "")

        pz2_sheet = book.sheet_by_name("ПЗ2")
        expected_doctors = [
            "Терапевт Казаков И.В.",
            "Хирург Конюк М.В.",
            "Стоматолог Шадрикова Ю.А.",
        ]
        for index, expected_doctor in enumerate(expected_doctors):
            row_index = PROF_EXTRACT_DOCTOR_ROWS[index][2]
            self.assertEqual(pz2_sheet.cell_value(row_index, PROF_EXTRACT_SEQUENCE_COL), float(index + 1))
            self.assertEqual(pz2_sheet.cell_value(row_index, PROF_EXTRACT_DOCTOR_COL), expected_doctor)

        first_unused_row = PROF_EXTRACT_DOCTOR_ROWS[len(expected_doctors)][2]
        self.assertEqual(pz2_sheet.cell_value(first_unused_row, PROF_EXTRACT_SEQUENCE_COL), "")
        self.assertEqual(pz2_sheet.cell_value(first_unused_row, PROF_EXTRACT_DOCTOR_COL), "")


if __name__ == "__main__":
    unittest.main()
