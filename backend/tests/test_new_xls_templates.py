from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

import xlrd
from xlutils.copy import copy as copy_xls_workbook


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.document_generator import (  # noqa: E402
    _apply_print_variant_to_xls_workbook,
    _generate_runtime_xls,
)
from app.services.new_xls_templates import (  # noqa: E402
    NEW_XLS_TEMPLATE_SPECS,
    strip_new_xls_placeholder_padding,
)
from app.services.seed import SERVICE_CATALOG  # noqa: E402
from app.services.template_catalog import (  # noqa: E402
    FOLDER_TEMPLATE_SOURCE_NAMES,
    TEMPLATE_DISPLAY_NAMES,
    load_template_catalog,
)


TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates"


def exam(
    role_id: str,
    doctor_name: str,
    *,
    diagnosis: str = "",
    result_text: str = "",
    fields: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        doctor_role_id=role_id,
        doctor_name=doctor_name,
        diagnosis=diagnosis,
        result_text=result_text,
        fields_json=fields or {},
        completed_at=datetime(2026, 7, 30, 10, 0),
        is_completed=True,
    )


class NewXlsTemplatesTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.client = SimpleNamespace(birth_date=date(1988, 4, 12))
        self.encounter = SimpleNamespace(encounter_date=date(2026, 7, 30))
        self.context = {
            "ClientCalc": "Проверкин Алексей Сергеевич",
            "BirthDateCalc_DAY": "12",
            "BirthDateCalc_DATEMONTH": "апреля",
            "BirthDateCalc_YEAR": "1988",
            "SexCalc": "муж",
            "SexFull": "мужской",
            "AddressCalc": "г. Санкт-Петербург, Невский проспект, д. 10, корп. 2, кв. 15",
            "CityCalc": "Санкт-Петербург",
            "DistrictCalc": "Центральный",
            "StreetCalc": "Невский проспект",
            "HouseNumberCalc": "10",
            "HouseBodyCalc": "2",
            "ApartmentNumberCalc": "15",
            "Phone": "+7 999 123-45-67",
            "DocumentSeries": "4010",
            "DocumentNumber": "123456",
            "DocumentDate": "01.02.2015",
            "SNILS": "123-456-789 01",
            "PolisOMS": "1234567890123456",
            "ReferenceNumber": "REF-77",
            "BlankNumber": "7654321",
            "BlankFullNumber": "ГИМС 7654321",
            "Diagnosis": "Плоскостопие",
            "MKB10": "M21.4",
            "Conclusion": "Допущен",
            "Doctor": "Контекстный Врач",
            "PoolValidUntil": "30.01.2027",
            "SportEkg": "",
            "SportEkgConclusion": "",
            "SportConclusion": "",
        }
        self.exams = [
            exam(
                "chairman",
                "Председатель Тестов",
                diagnosis="Плоскостопие",
                result_text="Допущен",
                fields={
                    "mkb10": "M21.4",
                    "complaints": "Жалоб нет",
                    "anamnesis": "Без особенностей",
                    "objective": "Состояние удовлетворительное",
                    "conclusionText": "Допущен к занятиям",
                    "sportType": "Плавание",
                    "ekgConclusion": "ЭКГ без патологии",
                    "validUntil": "30.01.2027",
                    "sanatoriumName": "Санаторий Северный",
                    "voucherNumber": "П-909",
                },
            ),
            exam("therapist", "Терапевт Тестов", result_text="Годен"),
            exam("psychiatrist", "Психиатр Тестов", result_text="Противопоказаний нет"),
            exam(
                "psychiatrist-narcologist",
                "Нарколог Тестов",
                result_text="Противопоказаний нет",
            ),
            exam("neurologist", "Невролог Тестов", result_text="Годен"),
            exam("ophthalmologist", "Офтальмолог Тестов", result_text="Годен"),
            exam("otolaryngologist", "ЛОР Тестов", result_text="Годен"),
            exam("surgeon", "Хирург Тестов", result_text="Годен"),
            exam("gynecologist", "Гинеколог Тестов", result_text="Годен"),
            exam("dermatologist", "Дерматолог Тестов", result_text="Годен"),
        ]

    def test_catalog_contains_all_new_templates(self):
        catalog = load_template_catalog()
        catalog_names = {item["file_name"] for item in catalog}
        expected_names = {spec.file_name for spec in NEW_XLS_TEMPLATE_SPECS}
        self.assertTrue(expected_names.issubset(catalog_names))
        display_name_by_file = {item["file_name"]: item["name"] for item in catalog}
        self.assertEqual(
            {file_name: display_name_by_file[file_name] for file_name in TEMPLATE_DISPLAY_NAMES},
            TEMPLATE_DISPLAY_NAMES,
        )
        description_by_file = {item["file_name"]: item["description"] for item in catalog}
        for file_name, source_name in FOLDER_TEMPLATE_SOURCE_NAMES.items():
            self.assertEqual(
                description_by_file[file_name],
                f"Подготовлен из папки клиента: {source_name}",
            )

    def test_related_services_use_customer_excel_abbreviations(self):
        service_name_by_legacy_id = {legacy_id: name for legacy_id, _, name, _ in SERVICE_CATALOG}
        self.assertEqual(
            {
                legacy_id: service_name_by_legacy_id[legacy_id]
                for legacy_id in (2, 5, 7, 11, 24, 31, 37)
            },
            {
                2: "ГС",
                5: "спорт",
                7: "071У",
                11: "ГТ",
                24: "072 у СКК",
                31: "070у",
                37: "ГИМС",
            },
        )

    def test_templates_are_single_sheet_and_free_of_source_examples(self):
        legacy_values = (
            "Разина",
            "Казаков",
            "Яковлев",
            "Резник",
            "ГС 428",
            "БС 5288",
            "23072385",
            "315115",
            "Дубровая роща",
            "не установлено",
            "Остеохондроз",
            "03.10.2007",
            "29.10.1969",
        )
        for spec in NEW_XLS_TEMPLATE_SPECS:
            with self.subTest(template=spec.file_name):
                book = xlrd.open_workbook(
                    str(TEMPLATES_DIR / spec.file_name),
                    formatting_info=True,
                )
                self.assertEqual(book.sheet_names(), [spec.sheet_name])
                sheet = book.sheet_by_index(0)
                self.assertGreater(len(sheet.rowinfo_map), 0)
                self.assertGreater(len(sheet.colinfo_map), 0)
                all_text = "\n".join(
                    str(sheet.cell_value(row_index, col_index))
                    for row_index in range(sheet.nrows)
                    for col_index in range(sheet.ncols)
                    if sheet.cell_value(row_index, col_index) not in ("", None)
                ).casefold()
                for legacy_value in legacy_values:
                    self.assertNotIn(legacy_value.casefold(), all_text)

    def test_all_templates_fill_program_values(self):
        expected_cells = {
            "ГС": {
                (18, 9): "30.07.2026",
                (27, 11): "Проверкин Алексей Сергеевич",
                (31, 10): "12.04.1988",
                (38, 26): "Терапевт Тестов",
                (41, 26): "Председатель Тестов",
            },
            "CKK": {
                (14, 12): "30.07.2026",
                (18, 15): "Проверкин Алексей Сергеевич",
                (19, 7): "12.04.1988",
                (36, 33): "+7 999 123-45-67",
                (39, 11): "Санаторий Северный",
                (57, 22): "Председатель Тестов",
            },
            "CKK72": {
                (13, 12): "30.07.2026",
                (15, 14): "Проверкин Алексей Сергеевич",
                (16, 7): "12.04.1988",
                (42, 14): "Проверкин Алексей Сергеевич",
                (56, 1): "Жалоб нет",
                (58, 1): "Без особенностей",
                (90, 28): "Председатель Тестов",
            },
            "Спорт": {
                (12, 8): "30.07.2026",
                (13, 3): "Проверкин Алексей Сергеевич",
                (13, 13): "12.04.1988",
                (19, 7): "Плавание",
                (22, 2): "ЭКГ без патологии",
                (23, 3): "Допущен к занятиям",
                (27, 11): "Председатель Тестов",
            },
            "ГТ": {
                (16, 6): "30.07.2026",
                (22, 2): "Проверкин Алексей Сергеевич",
                (24, 4): "12.04.1988",
                (36, 9): "30.07.2026",
                (36, 15): "Нарколог Тестов",
                (38, 15): "Психиатр Тестов",
                (40, 15): "Невролог Тестов",
            },
            "Тр.Об": {
                (9, 18): "Годен",
                (9, 38): "Годен",
                (36, 5): "Председатель Тестов",
                (36, 25): "Председатель Тестов",
            },
            "Суда": {
                (7, 3): "7654321",
                (7, 30): "7654321",
                (14, 2): "Проверкин Алексей Сергеевич",
                (14, 28): "Проверкин Алексей Сергеевич",
                (36, 9): "Председатель Тестов",
                (36, 31): "Председатель Тестов",
            },
        }

        with tempfile.TemporaryDirectory() as temporary_dir:
            temporary_path = Path(temporary_dir)
            for spec in NEW_XLS_TEMPLATE_SPECS:
                with self.subTest(template=spec.file_name):
                    output_path = temporary_path / spec.file_name
                    _generate_runtime_xls(
                        TEMPLATES_DIR / spec.file_name,
                        output_path,
                        self.context,
                        self.client,
                        self.encounter,
                        {"exams": self.exams},
                        print_variant=spec.print_variant,
                    )
                    book = xlrd.open_workbook(str(output_path), formatting_info=True)
                    self.assertEqual(book.sheet_names(), [spec.sheet_name])
                    sheet = book.sheet_by_index(0)
                    for coordinate, expected_value in expected_cells[spec.sheet_name].items():
                        self.assertEqual(
                            strip_new_xls_placeholder_padding(sheet.cell_value(*coordinate)),
                            expected_value,
                        )

    def test_missing_values_clear_every_dynamic_cell(self):
        empty_context = {
            "Diagnosis": "Здоров",
            "Conclusion": "",
            "Doctor": "Врач",
        }
        empty_client = SimpleNamespace(birth_date=None)
        empty_encounter = SimpleNamespace(encounter_date=None)
        with tempfile.TemporaryDirectory() as temporary_dir:
            for spec in NEW_XLS_TEMPLATE_SPECS:
                with self.subTest(template=spec.file_name):
                    output_path = Path(temporary_dir) / spec.file_name
                    _generate_runtime_xls(
                        TEMPLATES_DIR / spec.file_name,
                        output_path,
                        empty_context,
                        empty_client,
                        empty_encounter,
                        {"exams": []},
                        print_variant=spec.print_variant,
                    )
                    sheet = xlrd.open_workbook(str(output_path)).sheet_by_index(0)
                    for coordinate in spec.dynamic_cells:
                        row_index, col_index = coordinate
                        value = (
                            sheet.cell_value(row_index, col_index)
                            if row_index < sheet.nrows and col_index < sheet.ncols
                            else ""
                        )
                        self.assertEqual(strip_new_xls_placeholder_padding(value), "")

    def test_gt_is_only_bound_to_gostaina_not_gto(self):
        source_book = xlrd.open_workbook(
            str(TEMPLATES_DIR / "ГТ.xls"),
            formatting_info=True,
        )
        target_book = copy_xls_workbook(source_book)
        _apply_print_variant_to_xls_workbook(target_book, "gostaina")
        self.assertEqual(
            [sheet.name for sheet in target_book._Workbook__worksheets],
            ["ГТ"],
        )

        target_book = copy_xls_workbook(source_book)
        with self.assertRaisesRegex(ValueError, "ГТО"):
            _apply_print_variant_to_xls_workbook(target_book, "gto")

    def test_new_print_variants_keep_the_expected_single_sheet(self):
        for spec in NEW_XLS_TEMPLATE_SPECS:
            with self.subTest(print_variant=spec.print_variant):
                source_book = xlrd.open_workbook(
                    str(TEMPLATES_DIR / spec.file_name),
                    formatting_info=True,
                )
                target_book = copy_xls_workbook(source_book)
                _apply_print_variant_to_xls_workbook(
                    target_book,
                    spec.print_variant,
                )
                self.assertEqual(
                    [sheet.name for sheet in target_book._Workbook__worksheets],
                    [spec.sheet_name],
                )


if __name__ == "__main__":
    unittest.main()
