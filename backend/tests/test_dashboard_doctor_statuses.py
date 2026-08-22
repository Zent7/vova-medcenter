from datetime import date
from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.dashboard import get_client_doctor_statuses  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.doctor_exam import DoctorExam  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.models.encounter_service import EncounterService  # noqa: E402
from app.models.service import Service  # noqa: E402


class DashboardDoctorStatusesTests(unittest.TestCase):
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
                encounter_date=date(2026, 7, 6),
                payment_type="cash",
                total_amount=0,
                status="draft",
            )
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _statuses(self):
        return get_client_doctor_statuses(client_ids=[1], encounter_ids=None, db=self.db)[0]

    def test_completed_gynecologist_is_returned_for_male_client(self):
        self.db.add(
            DoctorExam(
                id=1,
                client_id=1,
                encounter_id=1,
                doctor_role_id="gynecologist",
                is_completed=True,
                fields_json={},
            )
        )
        self.db.commit()

        status = self._statuses()

        self.assertIn("gynecologist", status.existing_doctor_role_ids)
        self.assertIn("gynecologist", status.completed_doctor_role_ids)

    def test_draft_gynecologist_is_existing_but_not_completed(self):
        self.db.add(
            DoctorExam(
                id=1,
                client_id=1,
                encounter_id=1,
                doctor_role_id="gynecologist",
                is_completed=False,
                fields_json={},
            )
        )
        self.db.commit()

        status = self._statuses()

        self.assertIn("gynecologist", status.existing_doctor_role_ids)
        self.assertNotIn("gynecologist", status.completed_doctor_role_ids)

    def test_has_glasses_is_false_without_chairman_mark(self):
        self.db.add(
            DoctorExam(
                id=1,
                client_id=1,
                encounter_id=1,
                doctor_role_id="chairman",
                is_completed=True,
                fields_json={"hasGlasses": False, "indicationGlasses": False},
            )
        )
        self.db.commit()

        self.assertFalse(self._statuses().has_glasses)

    def test_chairman_glasses_checkbox_sets_has_glasses(self):
        self.db.add(
            DoctorExam(
                id=1,
                client_id=1,
                encounter_id=1,
                doctor_role_id="chairman",
                is_completed=False,
                fields_json={"hasGlasses": True},
            )
        )
        self.db.commit()

        self.assertTrue(self._statuses().has_glasses)

    def test_chairman_glasses_indication_sets_has_glasses(self):
        self.db.add(
            DoctorExam(
                id=1,
                client_id=1,
                encounter_id=1,
                doctor_role_id="chairman",
                is_completed=True,
                fields_json={"indicationGlasses": True},
            )
        )
        self.db.commit()

        self.assertTrue(self._statuses().has_glasses)

    def test_requested_encounters_for_same_client_have_separate_statuses(self):
        self.db.add_all(
            [
                Service(id=1, code="old-service", name="Old service", price=100),
                Service(id=2, code="new-service", name="New service", price=200),
                Encounter(
                    id=2,
                    center_id=1,
                    client_id=1,
                    encounter_date=date(2026, 7, 7),
                    payment_type="cash",
                    total_amount=0,
                    status="draft",
                    suppressed_doctor_role_ids=["surgeon"],
                ),
            ]
        )
        self.db.flush()
        self.db.add_all(
            [
                EncounterService(encounter_id=1, service_id=1, unit_price=100, line_total=100),
                EncounterService(encounter_id=2, service_id=2, unit_price=200, line_total=200),
                DoctorExam(
                    client_id=1,
                    encounter_id=1,
                    doctor_role_id="therapist",
                    is_completed=True,
                    fields_json={},
                ),
                DoctorExam(
                    client_id=1,
                    encounter_id=2,
                    doctor_role_id="ophthalmologist",
                    is_completed=False,
                    fields_json={},
                ),
            ]
        )
        self.db.commit()

        statuses = get_client_doctor_statuses(
            client_ids=[1],
            encounter_ids=[2, 1, 2],
            db=self.db,
        )

        self.assertEqual([status.encounter_id for status in statuses], [2, 1])
        self.assertEqual([service.service_id for service in statuses[0].services], [2])
        self.assertEqual(statuses[0].existing_doctor_role_ids, ["ophthalmologist"])
        self.assertEqual(statuses[0].completed_doctor_role_ids, [])
        self.assertEqual(statuses[0].suppressed_doctor_role_ids, ["surgeon"])
        self.assertEqual([service.service_id for service in statuses[1].services], [1])
        self.assertEqual(statuses[1].existing_doctor_role_ids, ["therapist"])
        self.assertEqual(statuses[1].completed_doctor_role_ids, ["therapist"])

    def test_client_only_request_keeps_latest_encounter_compatibility(self):
        self.db.add(
            Encounter(
                id=2,
                center_id=1,
                client_id=1,
                encounter_date=date(2026, 7, 7),
                payment_type="cash",
                total_amount=0,
                status="closed",
            )
        )
        self.db.commit()

        statuses = get_client_doctor_statuses(client_ids=[1], encounter_ids=None, db=self.db)

        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0].client_id, 1)
        self.assertEqual(statuses[0].encounter_id, 2)
        self.assertEqual(statuses[0].encounter_status, "closed")


if __name__ == "__main__":
    unittest.main()
