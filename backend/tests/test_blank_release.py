from datetime import date, datetime
from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.models.blank_form import BLANK_STATUS_FREE, BLANK_STATUS_ISSUED, BlankBatch, BlankForm  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.document_journal import DocumentJournalEntry  # noqa: E402
from app.models.document_template import DocumentTemplate  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.models.generated_document import GeneratedDocument  # noqa: E402
from app.models.medical_record import MedicalRecord, MedicalRecordEntry  # noqa: E402
from app.services.blank_forms import BlankServiceError, release_form  # noqa: E402


class BlankReleaseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_release_returns_number_and_cancels_generated_artifacts(self):
        with self.Session() as db:
            center = Center(code="center", name="Центр")
            client = Client(patient_number=1, last_name="Иванов", first_name="Иван", birth_date=date(1980, 1, 1))
            template = DocumentTemplate(
                code="release_test",
                name="Справка",
                template_type="docx",
                file_name="template.docx",
                file_path="template.docx",
                output_format="docx",
                is_active=True,
            )
            db.add_all([center, client, template])
            db.flush()
            encounter = Encounter(
                center_id=center.id,
                client_id=client.id,
                encounter_date=date(2026, 7, 20),
                payment_type="cash",
            )
            batch = BlankBatch(
                center_id=center.id,
                blank_type="driver_medical_certificate",
                series="002",
                number_from=1,
                number_to=1,
                number_width=6,
                quantity=1,
            )
            db.add_all([encounter, batch])
            db.flush()
            blank = BlankForm(
                batch_id=batch.id,
                center_id=center.id,
                blank_type=batch.blank_type,
                series=batch.series,
                number_value=1,
                full_number="002000001",
                status=BLANK_STATUS_ISSUED,
                client_id=client.id,
                encounter_id=encounter.id,
                issued_at=datetime.utcnow(),
                issued_by_user_id=None,
            )
            db.add(blank)
            db.flush()
            generated = GeneratedDocument(
                encounter_id=encounter.id,
                client_id=client.id,
                template_id=template.id,
                document_number=blank.full_number,
                series=blank.series,
                blank_form_id=blank.id,
                blank_number_snapshot=blank.full_number,
                file_name="generated.docx",
                file_path="generated.docx",
            )
            db.add(generated)
            db.flush()
            blank.generated_document_id = generated.id
            journal = DocumentJournalEntry(
                journal_code="driver",
                journal_name="Журнал",
                generated_document_id=generated.id,
                client_id=client.id,
                encounter_id=encounter.id,
                number=blank.full_number,
            )
            record = MedicalRecord(client_id=client.id, center_id=center.id)
            db.add_all([journal, record])
            db.flush()
            record_entry = MedicalRecordEntry(
                medical_record_id=record.id,
                encounter_id=encounter.id,
                doctor_role_id="document",
                conclusion=f"Выдан номерной бланк медицинского заключения №{blank.full_number}",
            )
            db.add(record_entry)
            db.commit()

            released = release_form(db, form_id=blank.id, user_id=None)
            db.commit()

            self.assertEqual(released.status, BLANK_STATUS_FREE)
            self.assertIsNone(released.client_id)
            self.assertIsNone(released.encounter_id)
            self.assertIsNone(released.generated_document_id)
            self.assertIsNone(released.issued_at)
            db.refresh(generated)
            db.refresh(journal)
            self.assertIsNone(generated.blank_form_id)
            self.assertIsNone(generated.blank_number_snapshot)
            self.assertIsNotNone(generated.cancelled_at)
            self.assertIsNotNone(journal.deleted_at)
            self.assertIsNone(db.get(MedicalRecordEntry, record_entry.id))

    def test_only_issued_number_can_be_released(self):
        with self.Session() as db:
            batch = BlankBatch(
                blank_type="driver_medical_certificate",
                series="002",
                number_from=1,
                number_to=1,
                number_width=6,
                quantity=1,
            )
            db.add(batch)
            db.flush()
            blank = BlankForm(
                batch_id=batch.id,
                blank_type=batch.blank_type,
                series=batch.series,
                number_value=1,
                full_number="002000001",
                status=BLANK_STATUS_FREE,
            )
            db.add(blank)
            db.commit()

            with self.assertRaisesRegex(BlankServiceError, "только выданный"):
                release_form(db, form_id=blank.id, user_id=None)


if __name__ == "__main__":
    unittest.main()
