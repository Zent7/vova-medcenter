from datetime import date
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import xlrd
from xlutils.copy import copy as copy_xls_workbook

from app.services.document_generator import _generate_runtime_xls, _health_group_mark
from app.services.new_xls_templates import (
    LEGACY_XLS_TEMPLATE_BY_FILE,
    legacy_xls_marker_locations,
    legacy_xls_placeholder,
    strip_new_xls_placeholder_padding,
)


TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates"
SPEC = LEGACY_XLS_TEMPLATE_BY_FILE["профосмотр 29н.xls"]
EXPECTED_PRINTED_VALUES = {
    "blank_number": "7654321",
    "narcologist": "Психиатров П.П.",
    "patient_name": "Проверкин Алексей Сергеевич",
    "sex": "мужской",
    "birth_date": "12.04.1988",
    "workplace": "ООО Проверка",
    "company": "ООО Проверка",
    "department": "Цех № 3",
    "position": "Электрогазосварщик",
    "psychiatrist": "Психиатров П.П.",
    "harmfulness": "Приложение 1 п. 4.1",
    "health_group": "II",
    "chairman": "Терапевтова Т.Т.",
    "position_repeat": "Электрогазосварщик",
    "occupational_doctor": "Терапевтова Т.Т.",
    "issue_date": "21.09.2026",
}


def print_conclusion(template_path: Path, output_path: Path) -> None:
    _generate_runtime_xls(
        template_path,
        output_path,
        {
            "ClientCalc": "Проверкин Алексей Сергеевич",
            "SexFull": "мужской",
            "WorkPlace": "ООО Проверка",
            "CompanyName": "ООО Проверка",
            "Department": "Цех № 3",
            "Post": "Электрогазосварщик",
            "Harmfulness": "Приложение 1 п. 4.1",
            "HealthGroup": "II группа здоровья",
            "BlankNumber": "7654321",
        },
        SimpleNamespace(
            birth_date=date(1988, 4, 12),
            sex="M",
            admission_category="",
            indications="",
            doctor_therapist="Терапевтова Т.Т.",
            doctor_psychiatrist="Психиатров П.П.",
        ),
        SimpleNamespace(encounter_date=date(2026, 9, 21)),
        {"exams": [], "service_names": []},
    )


def printed_values(template_path: Path, output_path: Path) -> dict[str, str]:
    """Что напечаталось на месте каждой метки в шаблоне."""
    locations = legacy_xls_marker_locations(xlrd.open_workbook(str(template_path), formatting_info=True), SPEC)
    printed_book = xlrd.open_workbook(str(output_path), formatting_info=True)
    return {
        field_id: strip_new_xls_placeholder_padding(printed_book.sheet_by_name(sheet_name).cell_value(row, col))
        for field_id, (sheet_name, row, col) in locations.items()
    }


class ProfConclusion29nTests(unittest.TestCase):
    def test_health_group_keeps_only_the_numeral(self):
        """Клетка «Группа здоровья» в 29н узкая, туда влезает только номер."""
        for value, expected in [
            ("I группа здоровья", "I"),
            ("II группа здоровья", "II"),
            ("III группа здоровья, Д-наблюдение", "III"),
            ("IV группа здоровья", "IV"),
            ("V группа здоровья", "V"),
            ("I", "I"),
        ]:
            with self.subTest(value=value):
                self.assertEqual(_health_group_mark(value), expected)

    def test_health_group_longest_numeral_wins(self):
        """IV не должна усечься до I: порядок альтернатив в разборе значим."""
        self.assertEqual(_health_group_mark("IV группа здоровья"), "IV")
        self.assertEqual(_health_group_mark("III группа здоровья"), "III")

    def test_free_text_health_group_is_kept_as_is(self):
        for value in ("основная", "не установлена", "подготовительная"):
            with self.subTest(value=value):
                self.assertEqual(_health_group_mark(value), value)

    def test_empty_health_group_prints_nothing(self):
        for value in ("", "   ", None):
            with self.subTest(value=value):
                self.assertEqual(_health_group_mark(value), "")

    def test_conclusion_29n_spec_covers_the_customer_sheet(self):
        spec = LEGACY_XLS_TEMPLATE_BY_FILE["профосмотр 29н.xls"]
        self.assertEqual(spec.sheet_names, ("ПРОФОСМОТР",))
        field_ids = {field.field_id for field in spec.fields}
        for required in (
            "blank_number",
            "patient_name",
            "birth_date",
            "company",
            "position",
            "health_group",
            "chairman",
            "issue_date",
        ):
            self.assertIn(required, field_ids)


class ProfConclusion29nPrintTests(unittest.TestCase):
    def test_bundled_template_prints_every_field_on_its_label(self):
        template_path = TEMPLATES_DIR / SPEC.file_name
        with tempfile.TemporaryDirectory() as temporary_dir:
            output_path = Path(temporary_dir) / "printed.xls"

            print_conclusion(template_path, output_path)

            self.assertEqual(printed_values(template_path, output_path), EXPECTED_PRINTED_VALUES)

    def test_customer_layout_over_the_old_value_cells_keeps_the_values(self):
        """Заказчик растянул подписи дат на клетки значений и перенёс метки ниже.

        На старых клетках теперь середина объединения с форматом General:
        посчитанные там значения ломали печать (KeyError в xlrd) или выводили
        дату серийным числом вроде 46286.
        """
        fields = {field.field_id: field for field in SPEC.fields}
        with tempfile.TemporaryDirectory() as temporary_dir:
            customer_copy = Path(temporary_dir) / "customer" / SPEC.file_name
            customer_copy.parent.mkdir()
            source_book = xlrd.open_workbook(str(TEMPLATES_DIR / SPEC.file_name), formatting_info=True)
            edited_book = copy_xls_workbook(source_book)
            sheet = edited_book.get_sheet(0)
            merged_ranges = sheet._Worksheet__merged_ranges
            for field_id, label_cell, moved_to in (
                ("birth_date", (22, 11), (47, 2)),
                ("issue_date", (45, 1), (48, 2)),
            ):
                row, col = fields[field_id].source_cell
                merged_ranges[:] = [
                    item
                    for item in merged_ranges
                    if not (item[0] <= row <= item[1] and item[2] <= col <= item[3])
                ]
                sheet.merge(label_cell[0], row, label_cell[1], col + 2)
                sheet.write(*moved_to, legacy_xls_placeholder(SPEC, fields[field_id]))
            edited_book.save(str(customer_copy))
            customer_book = xlrd.open_workbook(str(customer_copy), formatting_info=True)
            self.assertEqual(legacy_xls_marker_locations(customer_book, SPEC)["birth_date"][1:], (47, 2))
            output_path = Path(temporary_dir) / "printed.xls"

            print_conclusion(customer_copy, output_path)

            self.assertEqual(printed_values(customer_copy, output_path), EXPECTED_PRINTED_VALUES)


if __name__ == "__main__":
    unittest.main()
