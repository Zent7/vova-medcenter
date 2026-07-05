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
        return get_client_doctor_statuses(client_ids=[1], db=self.db)[0]

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


if __name__ == "__main__":
    unittest.main()
