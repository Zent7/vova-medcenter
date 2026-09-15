import json
from datetime import date, datetime, timezone
from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.doctor_exam import DoctorExam  # noqa: E402
from app.models.encounter_service import EncounterService
from app.models.medical_record import MedicalRecordEntry
from app.models.encounter import Encounter  # noqa: E402
from app.models.service import DoctorRole, Service, ServiceDoctorRole  # noqa: E402
from app.services.medical_autofill import autofill_completed_doctors_for_service  # noqa: E402


class MedicalAutofillTests(unittest.TestCase):
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
                total_amount=0,
                status="draft",
                suppressed_doctor_role_ids=["therapist"],
            )
        )
        self.db.add(Service(id=1, code="medical", name="Medical", price=100))
        self.db.add_all(
            [
                DoctorRole(id=1, code="therapist", name="Therapist", sort_order=1),
                DoctorRole(id=2, code="surgeon", name="Surgeon", sort_order=2),
            ]
        )
        self.db.add_all(
            [
                ServiceDoctorRole(service_id=1, doctor_role_id=1),
                ServiceDoctorRole(service_id=1, doctor_role_id=2),
            ]
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_suppressed_doctor_is_not_recreated_during_service_autofill(self):
        self.db.add(
            DoctorExam(
                client_id=1,
                encounter_id=1,
                doctor_role_id="therapist",
                fields_json={},
                deleted_at=datetime.now(timezone.utc),
            )
        )
        self.db.commit()
        encounter = self.db.get(Encounter, 1)

        autofill_completed_doctors_for_service(self.db, encounter, 1)
        self.db.commit()

        exams = self.db.execute(
            select(DoctorExam)
            .where(DoctorExam.deleted_at.is_(None))
            .order_by(DoctorExam.doctor_role_id)
        ).scalars().all()
        self.assertEqual([exam.doctor_role_id for exam in exams], ["surgeon"])

    def check_certificate(self, legacy_id, categories, expected, notes_override=None):
        service = self.db.get(Service, 1)
        service.legacy_source_id = legacy_id
        encounter = self.db.get(Encounter, 1)
        encounter.suppressed_doctor_role_ids = []
        self.db.get(Client, 1).admission_category = "C D"
        for index, code in enumerate(("ophthalmologist", "neurologist", "otolaryngologist"), start=3):
            self.db.add(DoctorRole(id=index, code=code, name=code))
            self.db.add(ServiceDoctorRole(service_id=1, doctor_role_id=index))
        self.db.add(EncounterService(encounter_id=1, service_id=1,
            notes=notes_override if notes_override is not None else json.dumps({"categories": categories})))
        self.db.flush()
        autofill_completed_doctors_for_service(self.db, encounter, 1)
        self.db.flush()
        actual = set(self.db.scalars(select(DoctorExam.doctor_role_id)))
        self.assertEqual(actual, expected)
        self.assertEqual(set(self.db.scalars(select(MedicalRecordEntry.doctor_role_id))), expected)

    def test_driver_ab_ignores_full_service_list_and_stale_client_categories(self):
        self.check_certificate(8, ["A", "B"], {"therapist", "ophthalmologist"})

    def test_tractor_ab_uses_two_doctors(self):
        self.check_certificate(7, "А, Б", {"therapist", "ophthalmologist"})

    def test_driver_cd_uses_four_doctors(self):
        self.check_certificate(29, ["C", "D"], {"therapist", "ophthalmologist", "neurologist", "otolaryngologist"})

    def test_tractor_cd_uses_four_doctors(self):
        self.check_certificate(7, "А, В, С, Д", {"therapist", "ophthalmologist", "neurologist", "otolaryngologist"})

    def test_legacy_invalid_notes_use_client_categories(self):
        self.check_certificate(8, None, {"therapist", "ophthalmologist", "neurologist", "otolaryngologist"}, notes_override="not json")

    def test_explicit_empty_categories_do_not_restore_stale_cd(self):
        self.check_certificate(8, [], {"therapist", "ophthalmologist"})


if __name__ == "__main__":
    unittest.main()
