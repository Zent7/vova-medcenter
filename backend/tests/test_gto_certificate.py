from datetime import date
from decimal import Decimal
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
from app.models.encounter_service import EncounterService
from app.models.service import Service
from app.services import document_generator as generator
from app.services.seed import _ensure_service_catalog
from app.services.template_catalog import sync_document_template_catalog, template_is_listed_on_templates_page


def document_text(path):
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    return "".join(root.itertext())


class GtoCertificateTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.output = tempfile.TemporaryDirectory()
        self.old_service = Service(code="legacy-service-4", legacy_source_id=4, name="Справка ГТО 1144", price=1000)
        self.db.add(self.old_service)
        self.db.commit()
        self.old_id = self.old_service.id
        _ensure_service_catalog(self.db)
        sync_document_template_catalog(self.db)
        self.db.add_all([
            Center(id=1, code="test", name="Тест"),
            Client(id=1, patient_number=1, last_name="Иванов", first_name="Иван", middle_name="Иванович", birth_date=date(1990, 1, 28), reference_number="ГТО-123"),
            Encounter(id=1, client_id=1, center_id=1, encounter_date=date(2026, 9, 22), total_amount=1500, payment_type="cash"),
            EncounterService(encounter_id=1, service_id=self.old_id, quantity=1, unit_price=1500, line_total=1500),
            DoctorExam(client_id=1, encounter_id=1, doctor_role_id="therapist", doctor_name="Тестов Т.Т.", fields_json={}),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.output.cleanup()

    def generate(self, file_name):
        template = self.db.scalar(select(DocumentTemplate).where(DocumentTemplate.file_name == file_name))
        with patch.object(generator.settings, "generated_documents_dir", self.output.name):
            return generator.generate_document(self.db, template_id=template.id, template_code=None, client_id=1, encounter_id=1)

    def test_existing_service_is_updated_without_duplicate_and_contract_uses_exact_name(self):
        _ensure_service_catalog(self.db)
        services = self.db.scalars(select(Service).where(Service.legacy_source_id == 4)).all()
        self.assertEqual(len(services), 1)
        self.assertEqual(services[0].id, self.old_id)
        self.assertEqual(services[0].name, "справка ГТО")
        self.assertEqual(services[0].price, Decimal("1500.00"))
        result = self.generate("Договор_шаблон_2.docx")
        self.assertEqual(result.generated_fields["Services"], "справка ГТО")
        text = document_text(result.output_file_path)
        self.assertIn("справка ГТО", text)
        self.assertNotIn("1144", text)

    def test_new_certificate_is_listed_and_fills_patient_dates_and_therapist(self):
        self.assertTrue(template_is_listed_on_templates_page("ГТО_шаблон.docx"))
        result = self.generate("ГТО_шаблон.docx")
        text = document_text(result.output_file_path)
        for value in ("Иванов", "Иван", "Иванович", "28.01.90", "ГТО-123", "22.09.26", "22.09.2027", "Тестов Т.Т."):
            self.assertIn(value, text)
        self.assertNotRegex(text, r"\[[A-Za-z][^\]]*\]")
        self.assertIn("484н", text)

    def test_validity_uses_chairman_date_and_clamps_leap_day(self):
        self.db.add(DoctorExam(client_id=1, encounter_id=1, doctor_role_id="chairman", doctor_name="Другой Д.Д.", fields_json={"examDate": "29.02.2024"}))
        self.db.commit()
        result = self.generate("ГТО_шаблон.docx")
        text = document_text(result.output_file_path)
        self.assertIn("29.02.24", text)
        self.assertIn("28.02.2025", text)
        self.assertIn("Тестов Т.Т.", text)
        self.assertNotIn("Другой Д.Д.", text)

    def test_missing_therapist_does_not_invent_a_signature(self):
        self.db.query(DoctorExam).delete()
        self.db.commit()
        result = self.generate("ГТО_шаблон.docx")
        self.assertEqual(result.generated_fields["GtoTherapistDoctor"], "")


if __name__ == "__main__":
    unittest.main()
