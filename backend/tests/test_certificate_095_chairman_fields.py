from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET
import zipfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.doctor_exam import DoctorExam  # noqa: E402
from app.services.document_generator import (  # noqa: E402
    _certificate_095_context_overrides,
    _generate_docx,
)


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "templates"
    / "Templates"
    / "095У_справка_шаблон.docx"
)


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    return "".join(node.text or "" for node in root.iter(f"{{{W_NS}}}t"))


class Certificate095ChairmanFieldsTests(unittest.TestCase):
    def setUp(self):
        self.exam = DoctorExam(
            doctor_role_id="chairman",
            fields_json={
                "educationInstitution": "Гимназия № 227",
                "illnessDiagnosis": "ОРВИ",
                "sickLeaveEndDate": "15.09.2026",
                "sickLeaveExtensionStartDate": "16.09.2026",
                "sickLeaveExtensionEndDate": "20.09.2026",
                "diagnosis": "патология органа зрения не выявлено",
            },
        )

    def test_chairman_card_fills_the_095_rows(self):
        overrides = _certificate_095_context_overrides([self.exam])

        self.assertEqual(overrides["Certificate095EducationInstitution"], "Гимназия № 227")
        self.assertEqual(overrides["Certificate095Diagnosis"], "ОРВИ")
        self.assertEqual(overrides["Certificate095SickLeaveEnd"], "15.09.2026")
        self.assertEqual(overrides["Certificate095ExtensionStart"], "16.09.2026")
        self.assertEqual(overrides["Certificate095ExtensionEnd"], "20.09.2026")

    def test_general_diagnosis_field_does_not_leak_into_the_095(self):
        exam = DoctorExam(
            doctor_role_id="chairman",
            fields_json={"diagnosis": "патология органа зрения не выявлено"},
        )

        overrides = _certificate_095_context_overrides([exam])

        self.assertEqual(overrides["Certificate095Diagnosis"], "")

    def test_visit_without_a_chairman_leaves_the_rows_empty(self):
        overrides = _certificate_095_context_overrides([])

        self.assertEqual(
            set(overrides.values()),
            {""},
        )

    def test_generated_095_prints_the_entered_rows(self):
        context = {
            "ReferenceNumber": "0000042",
            "ClientCalc": "Иванов Иван Иванович",
            "qdfMain.BirthDate": "24.07.2010",
            "VisitDate": "10.09.2026",
            "VisitDate_DATEFULL": "10 сентября 2026 г.",
        }
        context.update(_certificate_095_context_overrides([self.exam]))

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / TEMPLATE_PATH.name

            _generate_docx(TEMPLATE_PATH, output_path, context)

            text = docx_text(output_path)

        self.assertIn("Гимназия № 227", text)
        self.assertIn("ОРВИ", text)
        self.assertIn("15.09.2026", text)
        self.assertIn("16.09.2026", text)
        self.assertIn("20.09.2026", text)
        self.assertNotIn("[Certificate095", text)


if __name__ == "__main__":
    unittest.main()
