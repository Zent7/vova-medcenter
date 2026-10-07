"""Бланк ВУ печатается целиком и там же, где его печатала программа заказчика.

Бланк 003-В/у — две части рядом на альбомном листе A4, лицевая и оборот
устроены одинаково. Программа заказчика заполняла обе и печатала лицевую
областью A1:AZ44 при масштабе 97 %, оборот — целым листом. В августе 2026
правую часть приняли за лишнюю копию: печать стирала её, прятала столбцы и
сужала область печати, а встроенная лицевая печатала только A:AA. Месяц
справка выходила заполненной наполовину, и правки шаблона этого не меняли.
Шрифты, от которых зависит, где поля лягут на бумаге, проверяет
test_xls_customer_fonts.py.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

import xlrd


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.document_generator import (  # noqa: E402
    _driver_document_context_overrides,
    _generate_runtime_xls,
)
from app.services.new_xls_templates import (  # noqa: E402
    LEGACY_XLS_TEMPLATE_BY_FILE,
    LEGACY_XLS_TEMPLATE_SPECS,
    NEW_XLS_TEMPLATE_SPECS,
    legacy_xls_marker_locations,
    new_xls_markers,
    strip_new_xls_placeholder_padding,
)


TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates"
CENTER_SETS_DIR = TEMPLATES_DIR.parent / "Centers"
DRIVER_SIDES = (
    ("водительская лицевая.xls", "driver_front"),
    ("водительская обратн ст.xls", "driver_back"),
)


def print_areas(book) -> dict[int, tuple[int, int, int, int]]:
    """Номер листа -> (первая строка, строка за последней, первый столбец, столбец за последним)."""
    return {
        name.scope: name.area2d(clipped=False)[1:]
        for name in book.name_obj_list
        if name.builtin and name.name == "Print_Area"
    }


def new_xls_marker_locations(book, spec) -> dict[str, tuple[str, int, int]]:
    sheet = book.sheet_by_name(spec.sheet_name)
    locations: dict[str, tuple[str, int, int]] = {}
    for coordinate in spec.dynamic_cells:
        markers = new_xls_markers(spec, coordinate)
        for row_index in range(sheet.nrows):
            for col_index in range(sheet.ncols):
                value = sheet.cell_value(row_index, col_index)
                if isinstance(value, str) and any(marker in value for marker in markers):
                    locations[str(coordinate)] = (spec.sheet_name, row_index, col_index)
    return locations


def fields_off_paper(book, locations: dict[str, tuple[str, int, int]]) -> list[str]:
    """Поля, которые не попадут на бумагу: вне области печати или в скрытой строке/столбце."""
    areas = print_areas(book)
    problems: list[str] = []
    for field_id, (sheet_name, row_index, col_index) in locations.items():
        sheet_index = book.sheet_names().index(sheet_name)
        sheet = book.sheet_by_index(sheet_index)
        area = areas.get(sheet_index)
        if area is not None:
            first_row, end_row, first_col, end_col = area
            if not (first_row <= row_index < end_row and first_col <= col_index < end_col):
                problems.append(f"{field_id} ({row_index}, {col_index}) вне области печати {area}")
        column = sheet.colinfo_map.get(col_index)
        if column is not None and column.hidden:
            problems.append(f"{field_id} ({row_index}, {col_index}) в скрытом столбце")
        row = sheet.rowinfo_map.get(row_index)
        if row is not None and row.hidden:
            problems.append(f"{field_id} ({row_index}, {col_index}) в скрытой строке")
    return problems


def template_copies(file_name: str) -> list[Path]:
    """Встроенный бланк и его копии в начальных наборах центров."""
    center_copies = sorted(
        center_dir / file_name
        for center_dir in CENTER_SETS_DIR.iterdir()
        if center_dir.is_dir() and (center_dir / file_name).is_file()
    )
    return [TEMPLATES_DIR / file_name, *center_copies]


def right_part_field(field_id: str) -> str | None:
    """Поле правой части бланка для поля левой: у ограничений оборота это столбец 62 вместо 29."""
    if "_left" in field_id:
        return field_id.replace("_left", "_right")
    if field_id.startswith("restriction_") and field_id.endswith("_29"):
        return field_id.removesuffix("_29") + "_62"
    return None


def exam(role: str, doctor_name: str, fields: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        doctor_role_id=role,
        fields_json=fields or {},
        is_completed=True,
        doctor_name=doctor_name,
        diagnosis="",
        result_text="",
        completed_at=None,
    )


def print_driver_side(template_path: Path, output_path: Path, print_variant: str) -> None:
    client = SimpleNamespace(admission_category="B", indications="", birth_date=None)
    exams = [
        exam("therapist", "Сибирцев Вячеслав Александрович"),
        exam("ophthalmologist", "Цыганюк Юрий Сергеевич"),
        exam("chairman", "Председателев Пётр Ильич", {"categoryB": True, "restrictionAM": True}),
    ]
    context = {
        "ClientCalc": "Водилкин Максим Сергеевич",
        "BirthDateCalc_DAY": "01",
        "BirthDateCalc_DATEMONTH": "января",
        "BirthDateCalc_YEAR": "1990",
        "SubjectCalc": "Санкт-Петербург",
        "DistrictCalc": "Невский",
        "CityCalc": "Санкт-Петербург",
        "StreetCalc": "Бабушкина",
        "HouseNumberCalc": "222",
        "HouseBodyCalc": "333",
        "ApartmentNumberCalc": "444",
        "VisitDate_DATEMONTH": "сентября",
    }
    context.update(_driver_document_context_overrides(client, exams))
    _generate_runtime_xls(
        template_path,
        output_path,
        context,
        client,
        SimpleNamespace(encounter_date=date(2026, 9, 28)),
        {"exams": exams, "service_names": []},
        print_variant=print_variant,
    )


class BundledTemplatesPrintEveryFieldTests(unittest.TestCase):
    def test_every_field_of_a_free_layout_template_lands_on_paper(self):
        templates = [
            (spec.file_name, lambda book, spec=spec: legacy_xls_marker_locations(book, spec))
            for spec in LEGACY_XLS_TEMPLATE_SPECS
        ] + [
            (spec.file_name, lambda book, spec=spec: new_xls_marker_locations(book, spec))
            for spec in NEW_XLS_TEMPLATE_SPECS
        ]
        for file_name, locate in templates:
            # У копий ВУ из наборов центров область печати уже по полю «год выдачи»
            # справа; печать расширяет её сама, и это проверяет тест ниже.
            copies = [TEMPLATES_DIR / file_name] if file_name in dict(DRIVER_SIDES) else template_copies(file_name)
            for path in copies:
                with self.subTest(file_name=file_name, copy=path.parent.name):
                    book = xlrd.open_workbook(str(path), formatting_info=True)
                    locations = locate(book)
                    self.assertTrue(locations)
                    self.assertEqual(fields_off_paper(book, locations), [])


class DriverBlankPrintsBothPartsTests(unittest.TestCase):
    def test_both_parts_of_each_side_are_filled_alike_and_printed(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            for file_name, print_variant in DRIVER_SIDES:
                for template_path in template_copies(file_name):
                    with self.subTest(file_name=file_name, copy=template_path.parent.name):
                        output_path = Path(temporary_dir) / f"printed-{print_variant}.xls"
                        print_driver_side(template_path, output_path, print_variant)

                        spec = LEGACY_XLS_TEMPLATE_BY_FILE[file_name.casefold()]
                        template_book = xlrd.open_workbook(str(template_path), formatting_info=True)
                        locations = legacy_xls_marker_locations(template_book, spec)
                        printed_book = xlrd.open_workbook(str(output_path), formatting_info=True)

                        self.assertEqual(fields_off_paper(printed_book, locations), [])
                        self.assertFalse(
                            [col for col, column in printed_book.sheet_by_index(0).colinfo_map.items() if column.hidden]
                        )

                        def printed(field_id: str) -> str:
                            sheet_name, row_index, col_index = locations[field_id]
                            sheet = printed_book.sheet_by_name(sheet_name)
                            return strip_new_xls_placeholder_padding(sheet.cell_value(row_index, col_index))

                        pairs = [
                            (field.field_id, right_part_field(field.field_id))
                            for field in spec.fields
                            if right_part_field(field.field_id)
                        ]
                        # Каждое поле бланка стоит в паре: в левой части и в правой.
                        self.assertEqual(len(pairs) * 2, len(spec.fields))
                        for left_field, right_field in pairs:
                            self.assertEqual(printed(right_field), printed(left_field), right_field)
                        self.assertTrue([left_field for left_field, _ in pairs if printed(left_field)])

    def test_front_prints_like_the_customer_program(self):
        # Программа заказчика печатала лицевую областью A1:AZ44 при масштабе 97 %.
        book = xlrd.open_workbook(str(TEMPLATES_DIR / "водительская лицевая.xls"), formatting_info=True)
        self.assertEqual(print_areas(book), {0: (0, 44, 0, 52)})


if __name__ == "__main__":
    unittest.main()
