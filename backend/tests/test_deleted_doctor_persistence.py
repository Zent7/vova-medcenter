from datetime import date
from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.dashboard import get_client_doctor_statuses  # noqa: E402
from app.api.v1.routes.doctor_exams import delete_doctor_exam  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.doctor_exam import DoctorExam  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.models.service import DoctorRole, Service, ServiceDoctorRole  # noqa: E402
from app.services.medical_autofill import autofill_completed_doctors_for_service  # noqa: E402


class DeletedDoctorPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(Center(id=1, code="demo", name="Demo"))
        self.db.add(
            Client(
                id=1,
                patient_number=1,
                last_name="Ivanov",
                first_name="Ivan",
                birth_date=date(1990, 1, 1),
                sex="male",
            )
        )
        self.db.add(
            Encounter(
                id=1,
                center_id=1,
                client_id=1,
                encounter_date=date(2026, 8, 10),
                payment_type="cash",
                total_amount=100,
                status="draft",
            )
        )
        self.db.add(Service(id=1, code="medical", name="Medical", price=100))
        self.db.add(DoctorRole(id=1, code="therapist", name="Therapist", sort_order=1))
        self.db.add(ServiceDoctorRole(service_id=1, doctor_role_id=1))
        self.db.add(
            DoctorExam(
                id=1,
                client_id=1,
                encounter_id=1,
                doctor_role_id="therapist",
                fields_json={},
                is_completed=True,
            )
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_deleted_doctor_is_not_recreated_by_service_autofill(self):
        delete_doctor_exam(1, self.db)

        encounter = self.db.get(Encounter, 1)
        self.assertEqual(encounter.suppressed_doctor_role_ids, ["therapist"])

        autofill_completed_doctors_for_service(self.db, encounter, 1)
        self.db.commit()

        active_exams = self.db.execute(
            select(DoctorExam).where(DoctorExam.deleted_at.is_(None))
        ).scalars().all()
        self.assertEqual(active_exams, [])

        status = get_client_doctor_statuses(client_ids=[1], db=self.db)[0]
        self.assertEqual(status.completed_doctor_role_ids, [])
        self.assertEqual(status.suppressed_doctor_role_ids, ["therapist"])


if __name__ == "__main__":
    unittest.main()
