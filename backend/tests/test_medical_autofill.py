from datetime import date
from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.doctor_exam import DoctorExam  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.models.medical_record import MedicalRecordEntry  # noqa: E402
from app.models.service import DoctorRole, Service, ServiceDoctorRole  # noqa: E402
from app.services.medical_autofill import autofill_completed_doctors_for_service  # noqa: E402


class MedicalAutofillTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_autofill_completes_card_entries_but_keeps_suppressed_roles_removed(self):
        with self.Session() as db:
            center = Center(code="center", name="Центр")
            client = Client(
                patient_number=1,
                last_name="Иванов",
                first_name="Иван",
                birth_date=date(1980, 1, 1),
                sex="M",
            )
            service = Service(code="prof", name="Профосмотр")
            therapist = DoctorRole(code="therapist", name="Терапевт", sort_order=10)
            neurologist = DoctorRole(code="neurologist", name="Невролог", sort_order=20)
            db.add_all([center, client, service, therapist, neurologist])
            db.flush()
            db.add_all(
                [
                    ServiceDoctorRole(service_id=service.id, doctor_role_id=therapist.id),
                    ServiceDoctorRole(service_id=service.id, doctor_role_id=neurologist.id),
                ]
            )
            encounter = Encounter(
                center_id=center.id,
                client_id=client.id,
                encounter_date=date(2026, 8, 7),
                payment_type="cash",
                suppressed_doctor_role_ids=["neurologist"],
            )
            db.add(encounter)
            db.flush()

            autofill_completed_doctors_for_service(db, encounter, service.id)
            db.flush()

            exams = db.execute(select(DoctorExam).order_by(DoctorExam.doctor_role_id)).scalars().all()
            entries = db.execute(select(MedicalRecordEntry).order_by(MedicalRecordEntry.doctor_role_id)).scalars().all()
            self.assertEqual([item.doctor_role_id for item in exams], ["therapist"])
            self.assertTrue(exams[0].is_completed)
            self.assertEqual([item.doctor_role_id for item in entries], ["therapist"])
            self.assertTrue(entries[0].conclusion)


if __name__ == "__main__":
    unittest.main()
