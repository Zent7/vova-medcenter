from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

from fastapi import HTTPException, UploadFile
import xlrd
from xlutils.copy import copy as copy_xls_workbook


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.document_generator import (  # noqa: E402
    _apply_print_variant_to_xls_workbook,
    _generate_runtime_xls,
)
from app.services.new_xls_templates import (  # noqa: E402
    LEGACY_XLS_TEMPLATE_SPECS,
    NEW_XLS_TEMPLATE_SPECS,
    legacy_xls_placeholder,
    new_xls_placeholder,
    strip_new_xls_placeholder_padding,
    validate_editable_xls_template,
    validate_legacy_editable_xls_template,
)
from app.core.config import settings  # noqa: E402
from app.api.v1.routes.documents import replace_document_template, reset_document_template  # noqa: E402
from app.models.document_template import DocumentTemplate  # noqa: E402
from app.services.seed import SERVICE_CATALOG  # noqa: E402
from app.services.template_catalog import (  # noqa: E402
    ACTIVE_TEMPLATE_FILE_NAMES,
    FOLDER_TEMPLATE_SOURCE_NAMES,
    TEMPLATE_DISPLAY_NAMES,
    load_template_catalog,
    template_has_override,
    template_supports_layout_editing,
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
            "SubjectCalc": "Санкт-Петербург",
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
        self.assertEqual(catalog_names, set(ACTIVE_TEMPLATE_FILE_NAMES))
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
                if spec.file_name == "ГИМС (судна).xls":
                    self.assertNotIn("юлмед", all_text)

    def test_legacy_workbooks_contain_only_the_printable_sheets(self):
        expected_sheets = {
            "ВУ.xls": ["Водительская Лицевая", "Водительская Оборотная"],
            "АМБ_карты_профосмотр_шаблон.xls": ["Амб"],
            "Выписка из Амб карты (профа).xls": ["ПЗ2"],
            "Справка_342н_псих_освид.xls": ["Проф2"],
        }
        for file_name, sheet_names in expected_sheets.items():
            with self.subTest(template=file_name):
                book = xlrd.open_workbook(str(TEMPLATES_DIR / file_name), formatting_info=True)
                self.assertEqual(book.sheet_names(), sheet_names)

    def test_legacy_fields_generate_after_being_moved(self):
        legacy_client = SimpleNamespace(
            birth_date=date(1988, 4, 12),
            admission_category="B",
            indications="",
            document_type="Паспорт РФ",
            document_issued_date=None,
            doctor_therapist="",
            doctor_psychiatrist="",
            doctor_neurologist="",
            doctor_otolaryngologist="",
            doctor_surgeon="",
            doctor_gynecologist="",
            doctor_ophthalmologist="",
            doctor_dermatologist="",
            doctor_stomatologist="",
        )
        context = {
            **self.context,
            "CompanyName": "ООО Проверка",
            "Post": "Водитель",
            "Harmfulness": "Приказ 342н",
            "Services": "периодический осмотр",
            "VisitDate_DATEMONTH": "июля",
        }
        with tempfile.TemporaryDirectory() as temporary_dir:
            temporary_path = Path(temporary_dir)
            for spec in LEGACY_XLS_TEMPLATE_SPECS:
                with self.subTest(template=spec.file_name):
                    source_path = TEMPLATES_DIR / spec.file_name
                    baseline_path = temporary_path / f"baseline-{spec.file_name}"
                    _generate_runtime_xls(
                        source_path,
                        baseline_path,
                        context,
                        legacy_client,
                        self.encounter,
                        {"exams": self.exams},
                    )
                    field = next(
                        (item for item in spec.fields if item.field_id == "patient_name"),
                        spec.fields[0],
                    )
                    baseline_book = xlrd.open_workbook(str(baseline_path), formatting_info=True)
                    expected = strip_new_xls_placeholder_padding(
                        baseline_book.sheet_by_name(field.sheet_name).cell_value(*field.source_cell)
                    )
                    self.assertTrue(expected)

                    edited_dir = temporary_path / f"edited-{LEGACY_XLS_TEMPLATE_SPECS.index(spec)}"
                    edited_dir.mkdir()
                    edited_path = edited_dir / spec.file_name
                    source_book = xlrd.open_workbook(str(source_path), formatting_info=True)
                    edited_book = copy_xls_workbook(source_book)
                    source_sheet_index = source_book.sheet_names().index(field.sheet_name)
                    edited_sheet = edited_book.get_sheet(source_sheet_index)
                    destination = (source_book.sheet_by_index(source_sheet_index).nrows + 2, 0)
                    edited_sheet.write(*field.source_cell, "")
                    edited_sheet.write(*destination, legacy_xls_placeholder(spec, field))
                    edited_book.save(str(edited_path))
                    validate_legacy_editable_xls_template(edited_path, spec)

                    moved_output_path = temporary_path / f"moved-{spec.file_name}"
                    _generate_runtime_xls(
                        edited_path,
                        moved_output_path,
                        context,
                        legacy_client,
                        self.encounter,
                        {"exams": self.exams},
                    )
                    moved_sheet = xlrd.open_workbook(str(moved_output_path)).sheet_by_name(field.sheet_name)
                    self.assertEqual(
                        strip_new_xls_placeholder_padding(moved_sheet.cell_value(*destination)),
                        expected,
                    )
                    self.assertEqual(moved_sheet.cell_value(*field.source_cell), "")

    def test_preserved_amb_uses_marker_anchors_to_hide_empty_doctor_groups(self):
        spec = next(item for item in LEGACY_XLS_TEMPLATE_SPECS if item.file_name.startswith("АМБ_"))
        client = SimpleNamespace(
            birth_date=date(1988, 4, 12),
            document_type="Паспорт РФ",
            admission_category="",
            legacy_payload_json={},
            doctor_therapist="",
            doctor_psychiatrist="",
            doctor_neurologist="",
            doctor_otolaryngologist="",
            doctor_surgeon="",
            doctor_gynecologist="",
            doctor_ophthalmologist="",
            doctor_dermatologist="",
            doctor_stomatologist="",
        )
        source_path = TEMPLATES_DIR / spec.file_name
        marker_book = xlrd.open_workbook(str(source_path), formatting_info=True)
        from app.services.new_xls_templates import legacy_xls_marker_locations

        locations = legacy_xls_marker_locations(marker_book, spec)
        with tempfile.TemporaryDirectory() as temporary_dir:
            output_path = Path(temporary_dir) / spec.file_name
            _generate_runtime_xls(
                source_path,
                output_path,
                {**self.context, "CompanyName": "ООО Проверка", "Post": "Водитель"},
                client,
                self.encounter,
                {"exams": self.exams[:4]},
            )
            sheet = xlrd.open_workbook(str(output_path), formatting_info=True).sheet_by_name("Амб")
            visible_rows = [
                locations[field.field_id][1]
                for field in spec.fields
                if field.field_id.startswith("exam_3_") or field.field_id.startswith("exam_4_")
            ]
            hidden_rows = [
                locations[field.field_id][1]
                for field in spec.fields
                if field.field_id.startswith("exam_5_") or field.field_id.startswith("exam_6_")
            ]
            self.assertFalse(sheet.rowinfo_map[min(visible_rows)].hidden)
            self.assertTrue(sheet.rowinfo_map[min(hidden_rows)].hidden)
            self.assertTrue(sheet.rowinfo_map[max(hidden_rows)].hidden)

    def test_legacy_validation_rejects_missing_and_duplicate_markers(self):
        spec = next(item for item in LEGACY_XLS_TEMPLATE_SPECS if item.sheet_names == ("ПЗ2",))
        field = spec.fields[0]
        source_path = TEMPLATES_DIR / spec.file_name
        with tempfile.TemporaryDirectory() as temporary_dir:
            temporary_path = Path(temporary_dir)
            source_book = xlrd.open_workbook(str(source_path), formatting_info=True)

            missing_path = temporary_path / "missing.xls"
            missing_book = copy_xls_workbook(source_book)
            missing_book.get_sheet(0).write(*field.source_cell, "")
            missing_book.save(str(missing_path))
            with self.assertRaisesRegex(ValueError, "Удалён скрытый маркер"):
                validate_legacy_editable_xls_template(missing_path, spec)

            duplicate_path = temporary_path / "duplicate.xls"
            duplicate_book = copy_xls_workbook(source_book)
            duplicate_book.get_sheet(0).write(90, 0, legacy_xls_placeholder(spec, field))
            duplicate_book.save(str(duplicate_path))
            with self.assertRaisesRegex(ValueError, "продублирован"):
                validate_legacy_editable_xls_template(duplicate_path, spec)

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
            "Тр.Лиц": {
                (7, 3): "7654321",
                (7, 30): "7654321",
                (14, 2): "Проверкин Алексей Сергеевич",
                (14, 28): "Проверкин Алексей Сергеевич",
                (15, 8): "12",
                (15, 15): "апреля",
                (15, 22): "1988",
                (17, 12): "Санкт-Петербург",
                (18, 4): "Центральный",
                (19, 6): "Санкт-Петербург",
                (20, 2): "Невский проспект",
                (21, 2): "10",
                (22, 2): "2",
                (22, 9): "15",
                (23, 12): "123-456-789 01",
                (26, 2): "30",
                (26, 11): "июля",
                (26, 21): "2026",
                (29, 12): "Терапевт Тестов Годен",
                (31, 12): "Офтальмолог Тестов Годен",
                (35, 12): "Невролог Тестов Годен",
                (37, 12): "ЛОР Тестов Годен",
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

    def test_field_marker_can_move_in_any_direction_and_out_of_order(self):
        spec = next(item for item in NEW_XLS_TEMPLATE_SPECS if item.sheet_name == "Суда")
        source_coordinate = spec.dynamic_cells[0]
        destination = (42, 8)
        with tempfile.TemporaryDirectory() as temporary_dir:
            edited_path = Path(temporary_dir) / spec.file_name
            output_path = Path(temporary_dir) / "generated.xls"
            source_book = xlrd.open_workbook(str(TEMPLATES_DIR / spec.file_name), formatting_info=True)
            edited_book = copy_xls_workbook(source_book)
            edited_sheet = edited_book.get_sheet(0)
            edited_sheet.write(*source_coordinate, "")
            edited_sheet.write(*destination, new_xls_placeholder(spec, source_coordinate))
            edited_book.save(str(edited_path))

            validate_editable_xls_template(edited_path, spec)
            _generate_runtime_xls(
                edited_path,
                output_path,
                self.context,
                self.client,
                self.encounter,
                {"exams": self.exams},
                print_variant=spec.print_variant,
            )
            generated_sheet = xlrd.open_workbook(str(output_path)).sheet_by_index(0)
            self.assertEqual(
                strip_new_xls_placeholder_padding(generated_sheet.cell_value(*destination)),
                "7654321",
            )
            self.assertEqual(generated_sheet.cell_value(*source_coordinate), "")

    def test_validation_rejects_missing_and_duplicate_markers(self):
        spec = next(item for item in NEW_XLS_TEMPLATE_SPECS if item.sheet_name == "Суда")
        coordinate = spec.dynamic_cells[0]
        with tempfile.TemporaryDirectory() as temporary_dir:
            temporary_path = Path(temporary_dir)
            source_book = xlrd.open_workbook(str(TEMPLATES_DIR / spec.file_name), formatting_info=True)

            missing_path = temporary_path / "missing.xls"
            missing_book = copy_xls_workbook(source_book)
            missing_book.get_sheet(0).write(*coordinate, "")
            missing_book.save(str(missing_path))
            with self.assertRaisesRegex(ValueError, "Удалён скрытый маркер"):
                validate_editable_xls_template(missing_path, spec)

            duplicate_path = temporary_path / "duplicate.xls"
            duplicate_book = copy_xls_workbook(source_book)
            duplicate_book.get_sheet(0).write(42, 8, new_xls_placeholder(spec, coordinate))
            duplicate_book.save(str(duplicate_path))
            with self.assertRaisesRegex(ValueError, "продублирован"):
                validate_editable_xls_template(duplicate_path, spec)

    def test_catalog_prefers_persistent_override_and_reports_capabilities(self):
        spec = next(item for item in NEW_XLS_TEMPLATE_SPECS if item.sheet_name == "Суда")
        original_override_dir = settings.document_template_overrides_dir
        with tempfile.TemporaryDirectory() as temporary_dir:
            try:
                settings.document_template_overrides_dir = temporary_dir
                override_path = Path(temporary_dir) / spec.file_name
                override_path.write_bytes((TEMPLATES_DIR / spec.file_name).read_bytes())
                catalog_item = next(item for item in load_template_catalog() if item["file_name"] == spec.file_name)
                self.assertEqual(Path(catalog_item["file_path"]), override_path)
                self.assertTrue(template_has_override(spec.file_name))
                self.assertTrue(template_supports_layout_editing(spec.file_name))
                for legacy_spec in LEGACY_XLS_TEMPLATE_SPECS:
                    self.assertTrue(template_supports_layout_editing(legacy_spec.file_name))
                self.assertFalse(template_supports_layout_editing("082у_шаблон.docx"))
            finally:
                settings.document_template_overrides_dir = original_override_dir

    def test_invalid_upload_is_atomic_and_reset_restores_builtin(self):
        spec = next(item for item in NEW_XLS_TEMPLATE_SPECS if item.sheet_name == "Суда")
        template = DocumentTemplate(
            id=701,
            code="gims-editable-test",
            name="ГИМС",
            file_name=spec.file_name,
            file_path=str(TEMPLATES_DIR / spec.file_name),
            description=None,
            template_type="xls",
            output_format="xls",
            requires_numbered_blank=True,
            blank_type="gims_medical_certificate",
            is_active=True,
        )

        class FakeDb:
            def get(self, model, object_id):
                return template if model is DocumentTemplate and object_id == template.id else None

            def commit(self):
                return None

            def refresh(self, item):
                return None

        original_override_dir = settings.document_template_overrides_dir
        with tempfile.TemporaryDirectory() as temporary_dir:
            try:
                settings.document_template_overrides_dir = temporary_dir
                source_book = xlrd.open_workbook(str(TEMPLATES_DIR / spec.file_name), formatting_info=True)
                invalid_book = copy_xls_workbook(source_book)
                invalid_book.get_sheet(0).write(*spec.dynamic_cells[0], "")
                invalid_path = Path(temporary_dir) / "invalid-source.xls"
                invalid_book.save(str(invalid_path))

                invalid_upload = UploadFile(filename=spec.file_name, file=BytesIO(invalid_path.read_bytes()))
                with self.assertRaises(HTTPException) as raised:
                    replace_document_template(template.id, invalid_upload, None, FakeDb())
                self.assertEqual(raised.exception.status_code, 400)
                override_path = Path(temporary_dir) / spec.file_name
                self.assertFalse(override_path.exists())
                self.assertEqual(template.file_path, str(TEMPLATES_DIR / spec.file_name))

                valid_upload = UploadFile(
                    filename=spec.file_name,
                    file=BytesIO((TEMPLATES_DIR / spec.file_name).read_bytes()),
                )
                response = replace_document_template(template.id, valid_upload, None, FakeDb())
                self.assertTrue(override_path.is_file())
                self.assertTrue(response.supports_layout_editing)
                self.assertTrue(response.has_override)

                reset_response = reset_document_template(template.id, None, FakeDb())
                self.assertFalse(override_path.exists())
                self.assertFalse(reset_response.has_override)
                self.assertEqual(Path(template.file_path), TEMPLATES_DIR / spec.file_name)
            finally:
                settings.document_template_overrides_dir = original_override_dir

    def test_invalid_legacy_upload_is_atomic(self):
        spec = next(item for item in LEGACY_XLS_TEMPLATE_SPECS if item.file_name == "ВУ.xls")
        template = DocumentTemplate(
            id=702,
            code="driver-editable-test",
            name="Водительская справка",
            file_name=spec.file_name,
            file_path=str(TEMPLATES_DIR / spec.file_name),
            description=None,
            template_type="xls",
            output_format="xls",
            requires_numbered_blank=True,
            blank_type="driver_medical_certificate",
            is_active=True,
        )

        class FakeDb:
            def get(self, model, object_id):
                return template if model is DocumentTemplate and object_id == template.id else None

            def commit(self):
                return None

            def refresh(self, item):
                return None

        original_override_dir = settings.document_template_overrides_dir
        with tempfile.TemporaryDirectory() as temporary_dir:
            try:
                settings.document_template_overrides_dir = temporary_dir
                source_book = xlrd.open_workbook(str(TEMPLATES_DIR / spec.file_name), formatting_info=True)
                invalid_book = copy_xls_workbook(source_book)
                field = spec.fields[0]
                invalid_book.get_sheet(source_book.sheet_names().index(field.sheet_name)).write(
                    *field.source_cell,
                    "",
                )
                invalid_path = Path(temporary_dir) / "invalid-driver.xls"
                invalid_book.save(str(invalid_path))

                invalid_upload = UploadFile(filename=spec.file_name, file=BytesIO(invalid_path.read_bytes()))
                with self.assertRaises(HTTPException) as raised:
                    replace_document_template(template.id, invalid_upload, None, FakeDb())
                self.assertEqual(raised.exception.status_code, 400)
                self.assertFalse((Path(temporary_dir) / spec.file_name).exists())
                self.assertEqual(template.file_path, str(TEMPLATES_DIR / spec.file_name))
            finally:
                settings.document_template_overrides_dir = original_override_dir


if __name__ == "__main__":
    unittest.main()
