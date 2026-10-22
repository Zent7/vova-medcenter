from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app.models  # noqa: F401,E402
from app.db.base import Base
from app.models.center import Center
from app.models.client import Client
from app.models.doctor_exam import DoctorExam
from app.models.document_template import DocumentTemplate
from app.models.encounter import Encounter
from app.services import document_generator as generator
from app.services.template_catalog import sync_document_template_catalog

ASSETS = Path(__file__).resolve().parents[2] / "assets" / "templates"
ECG_FILE_NAME = "ЭКГ_шаблон.docx"
ECG_TEMPLATE_PATHS = (
    ASSETS / "Templates" / ECG_FILE_NAME,
    ASSETS / "Centers" / "center-b" / ECG_FILE_NAME,
    ASSETS / "Centers" / "center-c" / ECG_FILE_NAME,
)


def document_text(path):
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    return "".join(root.itertext())


class EkgTemplateFilesTests(unittest.TestCase):
    def test_every_ecg_blank_takes_the_patient_and_the_study_from_the_card(self):
        for path in ECG_TEMPLATE_PATHS:
            with self.subTest(path=str(path.relative_to(ASSETS))):
                text = document_text(path)
                for token in ("[ClientCalc]", "[BirthDate]", "[EkgDate]", "[EkgConclusion]", "[EkgTherapistDoctor]"):
                    self.assertIn(token, text)
                self.assertNotIn("Сибирцев", text)
                self.assertNotIn("Синусовый водитель ритма", text)


class EkgCertificateTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.output = tempfile.TemporaryDirectory()
        sync_document_template_catalog(self.db)
        self.db.add_all([
            Center(id=1, code="test", name="Тест"),
            Client(id=1, patient_number=1, last_name="Иванов", first_name="Иван", middle_name="Иванович", birth_date=date(1990, 1, 28), reference_number="ЭКГ-1"),
            Encounter(id=1, client_id=1, center_id=1, encounter_date=date(2026, 10, 22), total_amount=700, payment_type="cash"),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.output.cleanup()

    def add_exam(self, role, name, **fields):
        self.db.add(DoctorExam(client_id=1, encounter_id=1, doctor_role_id=role, doctor_name=name, fields_json=fields))
        self.db.commit()

    def generate(self):
        template = self.db.scalar(select(DocumentTemplate).where(DocumentTemplate.file_name == ECG_FILE_NAME))
        with patch.object(generator.settings, "generated_documents_dir", self.output.name):
            return generator.generate_document(self.db, template_id=template.id, template_code=None, client_id=1, encounter_id=1)

    def test_card_fills_date_conclusion_and_therapist(self):
        self.add_exam("therapist", "Тестов Т.Т.")
        self.add_exam(
            "chairman",
            "Председателев П.П.",
            ekg="ЭКГ от 21.10.2026",
            ekgConclusion="Ритм синусовый, ЧСС 72, ЭОС нормальное, ЭКГ без особенностей от 21.10.2026",
        )
        result = self.generate()
        text = document_text(result.output_file_path)

        self.assertIn("Иванов Иван Иванович", text)
        self.assertIn("28.01.90", text)
        self.assertIn("ЭКГ от 21.10.2026 г.", text)
        self.assertIn("Ритм синусовый, ЧСС 72, ЭОС нормальное, ЭКГ без особенностей от 21.10.2026", text)
        self.assertIn("Врач: Тестов Т.Т.", text)
        self.assertNotRegex(text, r"\[[A-Za-z][^\]]*\]")

    def test_therapist_falls_back_to_the_card_doctor_and_date_to_the_visit(self):
        self.add_exam("chairman", "Председателев П.П.", ekgConclusion="Норма")
        result = self.generate()
        text = document_text(result.output_file_path)

        self.assertIn("Врач: Председателев П.П.", text)
        self.assertEqual(result.generated_fields["EkgDate"], "22.10.2026")
        self.assertIn("ЭКГ от 22.10.2026 г.", text)
        self.assertNotRegex(text, r"\[[A-Za-z][^\]]*\]")


if __name__ == "__main__":
    unittest.main()
