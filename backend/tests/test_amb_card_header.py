"""Шапка амбулаторной карты 25у (АМБ_карты_профосмотр_шаблон.xls).

Дата рождения и дата визита печатаются текстом «ДД.ММ.ГГГГ»: клетка без формата
даты выводила серийный номер (27526 вместо 12.05.1975). Дома, корпус и квартира
идут за улицей, потому что в шаблоне нет отдельных клеток под них.
"""

from __future__ import annotations

from datetime import date, datetime
import os
from pathlib import Path
import sys
import tempfile
import unittest


os.environ.setdefault("ALLOW_SQLITE", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.models.client import Client  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.services import document_generator  # noqa: E402
from app.services.document_context import build_document_context  # noqa: E402

TEMPLATE = Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates" / "АМБ_карты_профосмотр_шаблон.xls"


class AmbDateTextTests(unittest.TestCase):
    def test_dates_are_printed_as_text(self):
        self.assertEqual(document_generator._amb_text_date(date(1975, 5, 12)), "12.05.1975")
        self.assertEqual(document_generator._amb_text_date(datetime(2026, 10, 18, 9, 30)), "18.10.2026")

    def test_empty_and_placeholder_dates_stay_empty(self):
        self.assertEqual(document_generator._amb_text_date(None), "")
        self.assertEqual(document_generator._amb_text_date(date(1900, 1, 1)), "")


class AmbStreetLineTests(unittest.TestCase):
    def test_house_body_and_flat_follow_the_street(self):
        context = {
            "StreetCalc": "ул. Ленина",
            "HouseNumberCalc": "5",
            "HouseBodyCalc": "2",
            "ApartmentNumberCalc": "12",
        }

        self.assertEqual(
            document_generator._amb_street_line(context, "unused"),
            "ул. Ленина, 5, корп. 2, кв. 12",
        )

    def test_missing_parts_are_skipped(self):
        context = {"StreetCalc": "ул. Ленина", "HouseNumberCalc": "5"}

        self.assertEqual(document_generator._amb_street_line(context, "unused"), "ул. Ленина, 5")

    def test_without_street_the_whole_address_is_kept(self):
        self.assertEqual(document_generator._amb_street_line({}, "г. Гатчина, ул. Ленина, 5"), "г. Гатчина, ул. Ленина, 5")


@unittest.skipUnless(TEMPLATE.is_file(), "нет встроенного шаблона АМБ-карты")
class AmbCardPrintTests(unittest.TestCase):
    def test_printed_card_has_text_birth_date_and_full_street_line(self):
        import xlrd

        client = Client(
            last_name="Иванов",
            first_name="Иван",
            middle_name="Иванович",
            birth_date=date(1975, 5, 12),
            sex="male",
            registration_text="Россия, Ленинградская обл., г. Гатчина, ул. Ленина, д. 5, корп. 2, кв. 12",
            address_text="Россия, Ленинградская обл., г. Гатчина, ул. Ленина, д. 5, корп. 2, кв. 12",
        )
        encounter = Encounter(
            id=1,
            client_id=1,
            center_id=1,
            encounter_date=date(2026, 10, 18),
            payment_type="cash",
            total_amount=0,
            status="draft",
        )
        context = build_document_context(client, encounter, service_names=["Профосмотр"])

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "amb.xls"
            document_generator._generate_runtime_xls(TEMPLATE, output, context, client, encounter, {"exams": []})
            sheet = xlrd.open_workbook(str(output), formatting_info=True).sheet_by_name("Амб")

            def printed(row: int, col: int) -> str:
                return str(sheet.cell(row, col).value).replace("​", "").strip()

            self.assertEqual(printed(18, 48), "12.05.1975")
            self.assertEqual(printed(22, 35), "ул. Ленина, 5, корп. 2, кв. 12")


if __name__ == "__main__":
    unittest.main()
