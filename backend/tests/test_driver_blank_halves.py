"""Бланк ВУ печатается целиком и там же, где его печатала программа заказчика.

Бланк 003-В/у — две части рядом на альбомном листе A4, лицевая и оборот
устроены одинаково. Программа заказчика заполняла обе и печатала лицевую
областью A1:AZ44 при масштабе 97 %, оборот — целым листом. В августе 2026
правую часть приняли за лишнюю копию: печать стирала её, прятала столбцы и
сужала область печати, а встроенная лицевая печатала только A:AA. Месяц
справка выходила заполненной наполовину, и правки шаблона этого не меняли.

У заказчика на всех компьютерах Excel 2021. Ширину столбцов и высоту строк
на бумаге Excel считает от шрифта книги. В шаблоне заказчика это Arial Cyr
10, а шаблоны, сохранённые в Microsoft 365, несут Aptos Narrow, которого в
Excel 2021 нет, и тогда справка расползается и уходит на второй лист.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
import shutil
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import xlrd


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import document_generator  # noqa: E402
from app.services.document_generator import (  # noqa: E402
    _driver_document_context_overrides,
    _generate_runtime_xls,
    _new_xls_workbook_stream,
    _use_customer_default_xls_font,
    _write_new_xls_stream_bytes,
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
DRIVER_SIDES = (
    ("водительская лицевая.xls", "driver_front"),
    ("водительская обратн ст.xls", "driver_back"),
)
_XFEXT_RECORD = 0x087D
_XFEXT_FONT_SCHEME = 0x000E


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


def right_part_field(field_id: str) -> str | None:
    """Поле правой части бланка для поля левой: у ограничений оборота это столбец 62 вместо 29."""
    if "_left" in field_id:
        return field_id.replace("_left", "_right")
    if field_id.startswith("restriction_") and field_id.endswith("_29"):
        return field_id.removesuffix("_29") + "_62"
    return None


def normal_style_font_scheme(path: Path) -> int | None:
    """Шрифт темы у стиля «Обычный»: 0 — нет, 2 — шрифт текста темы (Aptos Narrow)."""
    stream, _ = _new_xls_workbook_stream(path.read_bytes())
    offset = 0
    while offset + 4 <= len(stream):
        record_id, length = struct.unpack_from("<HH", stream, offset)
        payload = offset + 4
        if record_id == 0x000A:
            break
        if record_id == _XFEXT_RECORD and struct.unpack_from("<H", stream, payload + 14)[0] == 0:
            ext_offset = payload + 20
            for _ in range(struct.unpack_from("<H", stream, payload + 18)[0]):
                ext_type, ext_length = struct.unpack_from("<HH", stream, ext_offset)
                if ext_type == _XFEXT_FONT_SCHEME:
                    return stream[ext_offset + 4]
                ext_offset += ext_length
        offset = payload + length
    return None


def make_copy_saved_in_microsoft_365(path: Path) -> None:
    """Копия шаблона, как её сохраняет Excel из Microsoft 365: шрифт книги Aptos Narrow 11 из темы."""
    with mock.patch.object(document_generator, "DRIVER_XLS_DEFAULT_FONT", ("aptos narrow", 220)):
        _use_customer_default_xls_font(path)
    data = bytearray(path.read_bytes())
    stream, sectors = _new_xls_workbook_stream(bytes(data))
    offset = 0
    while offset + 4 <= len(stream):
        record_id, length = struct.unpack_from("<HH", stream, offset)
        payload = offset + 4
        if record_id == _XFEXT_RECORD and struct.unpack_from("<H", stream, payload + 14)[0] == 0:
            ext_offset = payload + 20
            for _ in range(struct.unpack_from("<H", stream, payload + 18)[0]):
                ext_type, ext_length = struct.unpack_from("<HH", stream, ext_offset)
                if ext_type == _XFEXT_FONT_SCHEME:
                    _write_new_xls_stream_bytes(data, sectors, ext_offset + 4, b"\x02")
                ext_offset += ext_length
            break
        offset = payload + length
    path.write_bytes(bytes(data))


def cell_fonts(path: Path) -> dict[tuple[int, int], tuple]:
    book = xlrd.open_workbook(str(path), formatting_info=True)
    sheet = book.sheet_by_index(0)
    fonts = {}
    for row_index in range(sheet.nrows):
        for col_index in range(sheet.ncols):
            font = book.font_list[book.xf_list[sheet.cell_xf_index(row_index, col_index)].font_index]
            fonts[(row_index, col_index)] = (font.name, font.height, font.weight, font.italic, font.colour_index)
    return fonts


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
            with self.subTest(file_name=file_name):
                book = xlrd.open_workbook(str(TEMPLATES_DIR / file_name), formatting_info=True)
                locations = locate(book)
                self.assertTrue(locations)
                self.assertEqual(fields_off_paper(book, locations), [])


class DriverBlankPrintsBothPartsTests(unittest.TestCase):
    def test_both_parts_of_each_side_are_filled_alike_and_printed(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            for file_name, print_variant in DRIVER_SIDES:
                with self.subTest(file_name=file_name):
                    template_path = TEMPLATES_DIR / file_name
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


class DriverBlankUsesTheCustomerFontTests(unittest.TestCase):
    def test_bundled_templates_use_arial_cyr_10_as_the_workbook_font(self):
        for file_name, _ in DRIVER_SIDES:
            with self.subTest(file_name=file_name):
                path = TEMPLATES_DIR / file_name
                book = xlrd.open_workbook(str(path), formatting_info=True)
                self.assertEqual((book.font_list[0].name, book.font_list[0].height), ("Arial Cyr", 200))
                self.assertEqual(book.xf_list[0].font_index, 0)
                self.assertIn(normal_style_font_scheme(path), (None, 0))

    def test_a_copy_saved_in_microsoft_365_prints_with_the_customer_font(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            for file_name, print_variant in DRIVER_SIDES:
                with self.subTest(file_name=file_name):
                    customer_copy = Path(temporary_dir) / file_name
                    shutil.copy2(TEMPLATES_DIR / file_name, customer_copy)
                    make_copy_saved_in_microsoft_365(customer_copy)
                    copy_book = xlrd.open_workbook(str(customer_copy), formatting_info=True)
                    self.assertEqual(copy_book.font_list[0].name, "Aptos Narrow")
                    self.assertEqual(normal_style_font_scheme(customer_copy), 2)
                    self.assertEqual(cell_fonts(customer_copy), cell_fonts(TEMPLATES_DIR / file_name))
                    output_path = Path(temporary_dir) / f"printed-{print_variant}.xls"

                    print_driver_side(customer_copy, output_path, print_variant)

                    printed_book = xlrd.open_workbook(str(output_path), formatting_info=True)
                    self.assertEqual((printed_book.font_list[0].name, printed_book.font_list[0].height), ("Arial Cyr", 200))
                    self.assertEqual(printed_book.xf_list[0].font_index, 0)
                    self.assertEqual(normal_style_font_scheme(output_path), 0)
                    # Клетки печатаются теми же шрифтами, что и в копии заказчика.
                    self.assertEqual(cell_fonts(output_path), cell_fonts(customer_copy))


if __name__ == "__main__":
    unittest.main()
