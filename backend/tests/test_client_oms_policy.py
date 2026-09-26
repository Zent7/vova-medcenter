from datetime import date
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

import xlrd


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.v1.routes.clients import normalize_payload  # noqa: E402
from app.schemas.client import ClientUpdate  # noqa: E402
from app.services.document_generator import _generate_runtime_xls  # noqa: E402
from app.services.new_xls_templates import strip_new_xls_placeholder_padding  # noqa: E402


EXTRACT_TEMPLATE = (
    Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates" / "Выписка из Амб карты (профа).xls"
)
# «5. Номер страхового полиса ОМС»: 24 клеточки, полис печатается в первые 16.
OMS_BOXES = [(33, col_index) for col_index in range(15, 39)]


class ClientOmsPolicyPayloadTests(unittest.TestCase):
    def payload(self):
        return dict(last_name="Проверкин", first_name="Иван", birth_date=date(1990, 1, 1))

    def test_update_without_policy_keeps_the_saved_one(self):
        data = normalize_payload(ClientUpdate(**self.payload(), snils="123-456-789 01"))
        self.assertNotIn("oms_policy", data)

    def test_explicit_policy_is_saved_and_empty_one_clears_it(self):
        data = normalize_payload(ClientUpdate(**self.payload(), oms_policy=" 1234567890123456 "))
        self.assertEqual(data["oms_policy"], "1234567890123456")
        data = normalize_payload(ClientUpdate(**self.payload(), oms_policy=" "))
        self.assertIsNone(data["oms_policy"])


class AmbulatoryExtractOmsPolicyTests(unittest.TestCase):
    def generate(self, policy: str):
        client = SimpleNamespace(
            birth_date=date(1990, 1, 2),
            document_type="Паспорт РФ",
            admission_category="",
            legacy_payload_json={},
            doctor_therapist="",
        )
        context = {
            "LastNameCalc": "Проверкин",
            "FirstNameCalc": "Иван",
            "PatronymicCalc": "Сергеевич",
            "CompanyName": "ООО Тест",
            "Services": "периодический осмотр",
            "PolisOMS": policy,
        }
        with tempfile.TemporaryDirectory() as temporary_dir:
            output_path = Path(temporary_dir) / EXTRACT_TEMPLATE.name
            _generate_runtime_xls(
                EXTRACT_TEMPLATE,
                output_path,
                context,
                client,
                SimpleNamespace(encounter_date=date(2026, 9, 25)),
                {"exams": []},
                print_variant="ambulatory_extract",
            )
            sheet = xlrd.open_workbook(str(output_path)).sheet_by_name("ПЗ2")
            return [strip_new_xls_placeholder_padding(sheet.cell_value(*cell)) for cell in OMS_BOXES]

    def test_policy_digits_fill_one_box_each(self):
        boxes = self.generate("1234 5678 9012 3456")
        self.assertEqual(boxes[:16], list("1234567890123456"))
        self.assertEqual(boxes[16:], [""] * 8)

    def test_missing_policy_leaves_the_boxes_blank(self):
        self.assertEqual(self.generate(""), [""] * len(OMS_BOXES))


if __name__ == "__main__":
    unittest.main()
