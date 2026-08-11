from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET
import zipfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.blank_form import BlankForm  # noqa: E402
from app.models.doctor_exam import DoctorExam  # noqa: E402
from app.services.document_generator import (  # noqa: E402
    _chairman_082_context_overrides,
    _generate_docx,
)


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "templates"
    / "Templates"
    / "082у_шаблон.docx"
)


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    return "".join(node.text or "" for node in root.iter(f"{{{W_NS}}}t"))


class ChairmanCertificate082Tests(unittest.TestCase):
    def setUp(self):
        self.template = SimpleNamespace(
            file_name=TEMPLATE_PATH.name,
            file_path=str(TEMPLATE_PATH),
        )
        self.exam = DoctorExam(
            doctor_role_id="chairman",
            fields_json={"country": "Сербия"},
        )
        self.blank = BlankForm(
            batch_id=1,
            blank_type="driver_medical_certificate",
            center_id=1,
            series="082у",
            number_value=17,
            full_number="082у0000017",
            status="free",
        )

    def test_country_and_shared_sequence_number_are_added_to_context(self):
        overrides = _chairman_082_context_overrides(
            self.template,
            [self.exam],
            self.blank,
        )

        self.assertEqual(overrides["Country"], "Сербия")
        self.assertEqual(overrides["ReferenceNumber"], "0000017")
        self.assertEqual(overrides["SeriesNumberCalc"], "0000017")

    def test_unrelated_template_is_not_changed(self):
        template = SimpleNamespace(file_name="Договор_шаблон.docx", file_path=None)

        self.assertEqual(
            _chairman_082_context_overrides(template, [self.exam], self.blank),
            {},
        )

    def test_generated_082_uses_entered_country_and_sequence_number(self):
        context = {
            "ReferenceNumber": "0000017",
            "SeriesNumberCalc": "0000017",
            "ClientCalc": "Иванов Иван Иванович",
            "BirthDateCalc": "24.07.1986",
            "VisitDate": "11.08.2026",
            "Country": "Сербия",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / TEMPLATE_PATH.name

            _generate_docx(TEMPLATE_PATH, output_path, context)

            text = docx_text(output_path)

        self.assertIn("МЕДИЦИНСКАЯ СПРАВКА № 0000017", text)
        self.assertIn("Страна: Сербия", text)
        self.assertNotIn("Болгария", text)


if __name__ == "__main__":
    unittest.main()
