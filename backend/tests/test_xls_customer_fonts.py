"""Бланки печатаются шрифтами книги заказчика и в любом Excel выходят одинаково.

Excel раскладывает столбцы и строки на бумаге по шрифту книги. Во всех книгах
старой программы заказчика это Arial Cyr 10 при стандартной теме Office, а
клетки, оформленные шрифтом темы, в них набраны Calibri. Шаблоны вырезаны из
этих книг в Excel из Microsoft 365 и унесли его тему 2023 года с Aptos Narrow.
У заказчика везде Excel 2021, где Aptos нет: Excel подставляет Arial, и бланк
расползается и уходит на второй лист.

fixtures/saved_in_microsoft_365 — шаблоны в том виде, в каком их скачивали со
страницы «Шаблоны» до исправления. Такие копии заказчика лежат на сайте.
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

import xlrd


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.document_generator import _generate_runtime_xls, _new_xls_workbook_stream  # noqa: E402
from app.services.new_xls_templates import (  # noqa: E402
    LEGACY_XLS_TEMPLATE_SPECS,
    NEW_XLS_TEMPLATE_BY_FILE,
    NEW_XLS_TEMPLATE_SPECS,
)


TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "saved_in_microsoft_365"
FREE_LAYOUT_FILE_NAMES = [spec.file_name for spec in (*NEW_XLS_TEMPLATE_SPECS, *LEGACY_XLS_TEMPLATE_SPECS)]
LEGACY_PRINT_VARIANTS = {
    "водительская лицевая.xls": "driver_front",
    "водительская обратн ст.xls": "driver_back",
    "Выписка из Амб карты (профа).xls": "ambulatory_extract",
    "АМБ_карты_профосмотр_шаблон.xls": "prof_ambulatory",
}
# Arial Cyr 10, в ЛМК — Arial 10: тот же шрифт под своим именем.
CUSTOMER_WORKBOOK_FONTS = {("Arial Cyr", 200), ("Arial", 200)}
DEFAULT_THEME_VERSION = 124226
THEME_FONT_NAMES = {"Aptos Narrow": "Calibri", "Aptos Display": "Calibri Light"}


def theme_version_and_normal_style_scheme(path: Path) -> tuple[int | None, int | None]:
    """Номер версии темы и шрифт темы у стиля «Обычный» (0 — нет, 2 — шрифт текста темы)."""
    stream, _ = _new_xls_workbook_stream(path.read_bytes())
    theme_version = scheme = None
    offset = 0
    while offset + 4 <= len(stream):
        record_id, length = struct.unpack_from("<HH", stream, offset)
        payload = offset + 4
        if record_id == 0x000A:
            break
        if record_id == 0x0896:
            theme_version = struct.unpack_from("<I", stream, payload + 12)[0]
        elif record_id == 0x087D and struct.unpack_from("<H", stream, payload + 14)[0] == 0:
            ext_offset = payload + 20
            for _ in range(struct.unpack_from("<H", stream, payload + 18)[0]):
                ext_type, ext_length = struct.unpack_from("<HH", stream, ext_offset)
                if ext_type == 0x000E:
                    scheme = stream[ext_offset + 4]
                ext_offset += ext_length
        offset = payload + length
    return theme_version, scheme


def printed_fonts(path: Path, rename: dict[str, str] | None = None) -> dict[tuple, tuple]:
    """Шрифт каждой клетки и каждого куска размеченного текста на листах книги."""
    book = xlrd.open_workbook(str(path), formatting_info=True)

    def describe(font_index: int) -> tuple:
        font = book.font_list[font_index]
        name = font.name.rstrip()
        return ((rename or {}).get(name, name), font.height, font.weight, font.italic, font.colour_index, font.underline_type)

    fonts: dict[tuple, tuple] = {}
    for sheet_index, sheet in enumerate(book.sheets()):
        for row_index in range(sheet.nrows):
            for col_index in range(sheet.ncols):
                fonts[(sheet_index, row_index, col_index)] = describe(book.xf_list[sheet.cell_xf_index(row_index, col_index)].font_index)
        for (row_index, col_index), runs in sheet.rich_text_runlist_map.items():
            for position, font_index in runs:
                fonts[(sheet_index, row_index, col_index, position)] = describe(font_index)
    return fonts


def print_variant_of(file_name: str) -> str | None:
    spec = NEW_XLS_TEMPLATE_BY_FILE.get(file_name.casefold())
    return spec.print_variant if spec is not None else LEGACY_PRINT_VARIANTS.get(file_name)


def print_like_the_service(template_path: Path, output_path: Path) -> None:
    _generate_runtime_xls(
        template_path,
        output_path,
        {
            "ClientCalc": "Проверкин Алексей Сергеевич",
            "LastName": "Проверкин",
            "FirstName": "Алексей",
            "MiddleName": "Сергеевич",
            "BirthDateCalc_DAY": "12",
            "BirthDateCalc_DATEMONTH": "апреля",
            "BirthDateCalc_YEAR": "1988",
        },
        SimpleNamespace(birth_date=date(1988, 4, 12), admission_category="B", indications="", sex="M"),
        SimpleNamespace(encounter_date=date(2026, 9, 28)),
        {"exams": [], "service_names": []},
        print_variant=print_variant_of(template_path.name),
    )


class CustomerWorkbookFontTests(unittest.TestCase):
    def assert_customer_workbook_fonts(self, path: Path) -> None:
        book = xlrd.open_workbook(str(path), formatting_info=True)
        self.assertIn((book.font_list[0].name, book.font_list[0].height), CUSTOMER_WORKBOOK_FONTS)
        self.assertEqual(book.xf_list[book.style_name_map["Normal"][1]].font_index, 0)
        theme_version, scheme = theme_version_and_normal_style_scheme(path)
        self.assertIn(theme_version, (None, DEFAULT_THEME_VERSION))
        self.assertIn(scheme, (None, 0))
        aptos = sorted({font[0] for font in printed_fonts(path).values() if font[0].startswith("Aptos")})
        self.assertEqual(aptos, [], "на бумагу не должен попадать Aptos: в Excel 2021 его нет")

    def test_bundled_templates_carry_the_customer_workbook_font(self):
        for file_name in FREE_LAYOUT_FILE_NAMES:
            with self.subTest(file_name=file_name):
                self.assert_customer_workbook_fonts(TEMPLATES_DIR / file_name)

    def test_a_copy_saved_in_microsoft_365_prints_with_the_customer_fonts(self):
        fixtures = sorted(FIXTURES_DIR.glob("*.xls"))
        self.assertTrue(fixtures)
        with tempfile.TemporaryDirectory() as temporary_dir:
            for fixture in fixtures:
                with self.subTest(file_name=fixture.name):
                    customer_copy = Path(temporary_dir) / "copy" / fixture.name
                    customer_copy.parent.mkdir(exist_ok=True)
                    shutil.copy2(fixture, customer_copy)
                    self.assertEqual(xlrd.open_workbook(str(customer_copy), formatting_info=True).font_list[0].name, "Aptos Narrow")
                    output_path = Path(temporary_dir) / f"printed-{fixture.name}"

                    print_like_the_service(customer_copy, output_path)

                    self.assert_customer_workbook_fonts(output_path)
                    # Клетки и разметка строк печатаются прежними шрифтами, только
                    # Aptos снова стал Calibri, как в книге заказчика.
                    self.assertEqual(printed_fonts(output_path), printed_fonts(customer_copy, THEME_FONT_NAMES))


if __name__ == "__main__":
    unittest.main()
