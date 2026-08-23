from pathlib import Path
from types import SimpleNamespace
from datetime import date
import tempfile
import sys
import unittest

import xlrd
from xlutils.copy import copy as copy_xls_workbook


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.document_generator import (  # noqa: E402
    _apply_print_variant_to_xls_workbook,
    _driver_categories_for_documents,
    _driver_document_context_overrides,
    _exam_map,
    _fill_driver_xls_sheets,
    _driver_xml_context_overrides,
    _generate_runtime_xls,
)


def client(admission_category="", indications=""):
    return SimpleNamespace(admission_category=admission_category, indications=indications, birth_date=None)


def chairman(fields, *, is_completed=True):
    return SimpleNamespace(
        doctor_role_id="chairman",
        fields_json=fields,
        is_completed=is_completed,
        doctor_name="Председатель",
        diagnosis="",
        result_text="",
        completed_at=None,
    )


def exam(role, doctor_name, fields=None, *, is_completed=True):
    return SimpleNamespace(
        doctor_role_id=role,
        fields_json=fields or {},
        is_completed=is_completed,
        doctor_name=doctor_name,
        diagnosis="",
        result_text="",
        completed_at=None,
    )


class DriverDocumentContextTests(unittest.TestCase):
    def test_completed_chairman_categories_override_client_categories(self):
        selected = _driver_categories_for_documents(
            client(admission_category="A B C D"),
            [chairman({"categoryB": True, "categoryC": True})],
        )

        self.assertEqual(selected, {"B", "C"})

    def test_falls_back_to_client_admission_category_without_completed_chairman(self):
        selected = _driver_categories_for_documents(
            client(admission_category="A B C1E Tm"),
            [chairman({"categoryD": True}, is_completed=False)],
        )

        self.assertEqual(selected, {"A", "B", "C1E", "Tm"})

    def test_legacy_default_driver_categories_are_treated_as_b_only(self):
        selected = _driver_categories_for_documents(
            client(admission_category="A B C D BE M"),
            [],
        )

        self.assertEqual(selected, {"B"})

        selected_from_chairman = _driver_categories_for_documents(
            client(),
            [
                chairman(
                    {
                        "categoryA": True,
                        "categoryB": True,
                        "categoryC": True,
                        "categoryD": True,
                        "categoryBE": True,
                        "categoryM": True,
                    }
                )
            ],
        )

        self.assertEqual(selected_from_chairman, {"B"})

    def test_legacy_category_e_expands_to_be_ce_de(self):
        selected = _driver_categories_for_documents(
            client(admission_category=""),
            [chairman({"categoryE": True})],
        )

        self.assertEqual(selected, {"BE", "CE", "DE"})

    def test_document_context_includes_categories_and_conditions(self):
        context = _driver_document_context_overrides(
            client(admission_category="A B C D"),
            [
                chairman(
                    {
                        "categoryB": True,
                        "categoryBE": True,
                        "categoryBoat": True,
                        "indicationManual": True,
                        "indicationAutomatic": False,
                        "indicationGlasses": True,
                        "restrictionAM": True,
                        "restrictionCCE": True,
                    }
                )
            ],
        )

        self.assertEqual(context["CategoryA"], "")
        self.assertEqual(context["CategoryB"], "X")
        self.assertEqual(context["BECalc"], "X")
        self.assertEqual(context["ManualControlCalc"], "true")
        self.assertEqual(context["AutomaticTransmissionCalc"], "false")
        self.assertEqual(context["VisionTCCalc"], "true")
        self.assertEqual(context["DriveShipCalc"], "true")
        self.assertEqual(context["TCA"], "X")
        self.assertEqual(context["TCB"], "X")
        self.assertEqual(context["TCC"], "X")

    def test_driver_indications_use_latest_chairman_draft(self):
        context = _driver_document_context_overrides(
            client(admission_category=""),
            [
                chairman(
                    {
                        "indicationManual": True,
                        "indicationAutomatic": True,
                        "indicationAcoustic": False,
                        "indicationGlasses": True,
                        "indicationHearingAid": False,
                    },
                    is_completed=False,
                )
            ],
        )

        self.assertEqual(context["ManualControlCalc"], "true")
        self.assertEqual(context["AutomaticTransmissionCalc"], "true")
        self.assertEqual(context["ParkingSystemCalc"], "false")
        self.assertEqual(context["VisionTCCalc"], "true")
        self.assertEqual(context["HearingTCCalc"], "false")

    def test_xml_context_uses_boolean_categories_and_restrictions(self):
        test_client = client(admission_category="A B C D")
        exams = [
            chairman(
                {
                    "categoryB": True,
                    "categoryC1": True,
                    "indicationManual": True,
                    "restrictionAM": True,
                    "restrictionBBE": False,
                }
            )
        ]

        xml_context = _driver_xml_context_overrides({}, test_client, exams)

        self.assertEqual(xml_context["ACalc"], "false")
        self.assertEqual(xml_context["BCalc"], "true")
        self.assertEqual(xml_context["C1Calc"], "true")
        self.assertEqual(xml_context["ManualControlCalc"], "true")
        self.assertEqual(xml_context["AutomaticTransmissionCalc"], "false")
        self.assertEqual(xml_context["CategoryACalc"], "true")
        self.assertEqual(xml_context["CategoryBCalc"], "true")

    def test_driver_xls_back_sheet_fills_categories_restrictions_and_signer(self):
        template_path = next(
            path
            for path in (Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates").glob("*.xls")
            if "Водительская Оборотная" in xlrd.open_workbook(str(path), on_demand=True).sheet_names()
        )
        source_book = xlrd.open_workbook(str(template_path), formatting_info=True)
        target_book = copy_xls_workbook(source_book)
        test_client = client(admission_category="A B C")
        exams = [
            chairman(
                {
                    "categoryB": True,
                    "categoryC": True,
                    "categoryTram": True,
                    "categoryC1E": True,
                    "restrictionAM": True,
                    "restrictionBBE": False,
                    "restrictionCCE": True,
                    "indicationManual": True,
                    "indicationAutomatic": False,
                    "indicationAcoustic": True,
                    "indicationGlasses": False,
                    "indicationHearingAid": True,
                }
            ),
            exam("therapist", "Терапевт", {"conclusion": "здоров"}),
        ]
        context = {
            "ClientCalc": "Иванов Иван Иванович",
            "BirthDateCalc_DAY": "01",
            "BirthDateCalc_DATEMONTH": "января",
            "BirthDateCalc_YEAR": "1990",
            "SubjectCalc": "Москва",
            "DistrictCalc": "",
            "CityCalc": "Москва",
            "StreetCalc": "Тестовая",
            "HouseNumberCalc": "1",
            "HouseBodyCalc": "",
            "ApartmentNumberCalc": "2",
            "VisitDate_DATEMONTH": "июля",
            "InstrumentalExamination": "ЭЭГ без патологии",
            "LaboratoryStudy": "Не установлено",
        }
        context.update(_driver_document_context_overrides(test_client, exams))

        _fill_driver_xls_sheets(
            source_book,
            target_book,
            context,
            test_client,
            SimpleNamespace(encounter_date=date(2026, 7, 2)),
            _exam_map(exams),
        )

        output_path = Path(tempfile.gettempdir()) / "driver_xls_back_sheet_test.xls"
        target_book.save(str(output_path))
        result_book = xlrd.open_workbook(str(output_path), formatting_info=True)
        back_sheet = result_book.sheet_by_name("Водительская Оборотная")

        expected_marks = ["Z", "✓", "✓", "Z", "Z", "Z", "Z", "✓", "Z", "Z", "Z", "Z", "Z", "Z", "✓", "Z"]
        self.assertEqual([back_sheet.cell_value(10, col) for col in range(2, 34, 2)], expected_marks)
        self.assertEqual([back_sheet.cell_value(10, col) for col in range(35, 67, 2)], [""] * 16)
        self.assertTrue(all(back_sheet.colinfo_map[col].hidden for col in range(34, 66)))
        self.assertEqual(back_sheet.cell_value(36, 8), "Председатель")
        self.assertEqual(back_sheet.cell_value(36, 41), "")
        for row_index, expected in [
            (14, "установлено"),
            (17, "установлено"),
            (20, "установлено"),
            (25, "установлено"),
            (27, "не установлено"),
            (29, "установлено"),
            (31, "не установлено"),
            (33, "установлено"),
        ]:
            self.assertEqual(back_sheet.cell_value(row_index, 29), expected)
            self.assertEqual(back_sheet.cell_value(row_index, 62), "")

    def test_driver_xls_front_sheet_writes_issue_date_as_text(self):
        template_path = Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates" / "ВУ.xls"
        source_book = xlrd.open_workbook(str(template_path), formatting_info=True)
        target_book = copy_xls_workbook(source_book)
        test_client = client()
        context = {
            "ClientCalc": "Иванов Иван Иванович",
            "BirthDateCalc_DAY": "11",
            "BirthDateCalc_DATEMONTH": "февраля",
            "BirthDateCalc_YEAR": "1991",
            "SubjectCalc": "Россия",
            "DistrictCalc": "",
            "CityCalc": "Москва",
            "StreetCalc": "Тестовая",
            "HouseNumberCalc": "1",
            "HouseBodyCalc": "",
            "ApartmentNumberCalc": "2",
            "VisitDate_DATEMONTH": "июля",
            "InstrumentalExamination": "Без отклонений",
            "LaboratoryStudy": "Без отклонений",
        }

        _fill_driver_xls_sheets(
            source_book,
            target_book,
            context,
            test_client,
            SimpleNamespace(encounter_date=date(2026, 7, 31)),
            {},
        )

        output_path = Path(tempfile.gettempdir()) / "driver_xls_front_date_test.xls"
        target_book.save(str(output_path))
        result_book = xlrd.open_workbook(str(output_path), formatting_info=True)
        front_sheet = result_book.sheet_by_name("Водительская Лицевая")

        for col_index, expected in [(15, "31"), (19, "июля"), (23, "2026")]:
            cell = front_sheet.cell(23, col_index)
            self.assertEqual(cell.value, expected)
            self.assertEqual(cell.ctype, xlrd.XL_CELL_TEXT)
        for col_index in (41, 45, 49):
            self.assertEqual(front_sheet.cell_value(23, col_index), "")
        self.assertTrue(all(front_sheet.colinfo_map[col].hidden for col in range(27, 66)))

    def test_driver_xls_back_sheet_marks_operator_selected_categories_only(self):
        template_path = Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates" / "ВУ.xls"
        source_book = xlrd.open_workbook(str(template_path), formatting_info=True)
        target_book = copy_xls_workbook(source_book)
        test_client = client(admission_category="A, B, C, BE, M")
        context = {
            "ClientCalc": "Иванов Иван Иванович",
            "InstrumentalExamination": "Не установлено",
            "LaboratoryStudy": "Не установлено",
        }
        context.update(_driver_document_context_overrides(test_client, []))

        _fill_driver_xls_sheets(
            source_book,
            target_book,
            context,
            test_client,
            SimpleNamespace(encounter_date=date(2026, 7, 31)),
            {},
        )

        output_path = Path(tempfile.gettempdir()) / "driver_xls_selected_categories_test.xls"
        target_book.save(str(output_path))
        result_book = xlrd.open_workbook(str(output_path), formatting_info=True)
        back_sheet = result_book.sheet_by_name("Водительская Оборотная")

        expected_marks = ["✓", "✓", "✓", "Z", "✓", "Z", "Z", "Z", "Z", "✓", "Z", "Z", "Z", "Z", "Z", "Z"]
        self.assertEqual([back_sheet.cell_value(10, col) for col in range(2, 34, 2)], expected_marks)
        self.assertEqual([back_sheet.cell_value(10, col) for col in range(35, 67, 2)], [""] * 16)

    def test_driver_print_variants_keep_only_selected_side(self):
        template_path = Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates" / "ВУ.xls"
        for variant, expected_sheet in [
            ("driver_front", "Водительская Лицевая"),
            ("driver_back", "Водительская Оборотная"),
        ]:
            source_book = xlrd.open_workbook(str(template_path), formatting_info=True)
            target_book = copy_xls_workbook(source_book)

            _apply_print_variant_to_xls_workbook(target_book, variant)

            output_path = Path(tempfile.gettempdir()) / f"driver_{variant}_single_side_test.xls"
            target_book.save(str(output_path))
            result_book = xlrd.open_workbook(str(output_path), formatting_info=True)

            self.assertEqual(result_book.sheet_names(), [expected_sheet])

    def test_driver_runtime_xls_print_variant_keeps_only_selected_side(self):
        template_path = Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates" / "ВУ.xls"
        context = {
            "ClientCalc": "Иванов Иван Иванович",
            "BirthDateCalc_DAY": "11",
            "BirthDateCalc_DATEMONTH": "февраля",
            "BirthDateCalc_YEAR": "1991",
            "SubjectCalc": "Россия",
            "DistrictCalc": "",
            "CityCalc": "Москва",
            "StreetCalc": "Тестовая",
            "HouseNumberCalc": "1",
            "HouseBodyCalc": "",
            "ApartmentNumberCalc": "2",
            "VisitDate_DATEMONTH": "июля",
            "InstrumentalExamination": "Без отклонений",
            "LaboratoryStudy": "Без отклонений",
        }
        runtime_values = {"exams": [], "service_names": []}

        for variant, expected_sheet in [
            ("driver_front", "Водительская Лицевая"),
            ("driver_back", "Водительская Оборотная"),
        ]:
            output_path = Path(tempfile.gettempdir()) / f"driver_runtime_{variant}_single_side_test.xls"
            _generate_runtime_xls(
                template_path,
                output_path,
                context,
                client(admission_category="B"),
                SimpleNamespace(encounter_date=date(2026, 7, 31)),
                runtime_values,
                print_variant=variant,
            )
            result_book = xlrd.open_workbook(str(output_path), formatting_info=True)

            self.assertEqual(result_book.sheet_names(), [expected_sheet])
            result_sheet = result_book.sheet_by_name(expected_sheet)
            hidden_range = range(27, 66) if variant == "driver_front" else range(34, 66)
            managed_cols = [col for col in hidden_range if col in result_sheet.colinfo_map]
            self.assertTrue(managed_cols)
            self.assertTrue(all(result_sheet.colinfo_map[col].hidden for col in managed_cols))
            self.assertTrue(all(result_sheet.colinfo_map[col].width == 0 for col in managed_cols))


if __name__ == "__main__":
    unittest.main()
