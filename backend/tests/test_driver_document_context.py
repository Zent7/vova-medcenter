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
    _driver_categories_for_documents,
    _driver_document_context_overrides,
    _exam_map,
    _fill_driver_xls_sheets,
    _driver_xml_context_overrides,
)


def client(admission_category="", indications=""):
    return SimpleNamespace(admission_category=admission_category, indications=indications)


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
            if path.stat().st_size == 2407424
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
        self.assertEqual([back_sheet.cell_value(10, col) for col in range(35, 67, 2)], expected_marks)
        self.assertEqual(back_sheet.cell_value(36, 8), "Председатель")
        self.assertEqual(back_sheet.cell_value(36, 41), "Председатель")
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
            self.assertEqual(back_sheet.cell_value(row_index, 62), expected)


if __name__ == "__main__":
    unittest.main()
