from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


os.environ.setdefault("ALLOW_SQLITE", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.doctor_roles import update_doctor_role  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.center_doctor_name import CenterDoctorName  # noqa: E402
from app.models.doctor_exam import DoctorExam  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.models.service import DoctorRole  # noqa: E402
from app.schemas.doctor_role import DoctorRoleUpdate  # noqa: E402


class DoctorRoleDirectoryTests(unittest.TestCase):
    """ФИО врача записывается в справочник своего медцентра и подтягивается в осмотры."""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

        center = Center(code="center-a", name="Медцентр 1")
        self.db.add(center)
        self.db.flush()
        self.center_id = center.id

        encounter = Encounter(
            center_id=self.center_id,
            client_id=1,
            encounter_date=date(2026, 9, 1),
            payment_type="cash",
            created_by_user_id=1,
        )
        self.db.add(encounter)
        self.db.flush()

        self.db.add(DoctorRole(id=8, code="therapist", name="Терапевт", sort_order=8, is_active=True))
        self.db.add(
            DoctorExam(
                client_id=1,
                encounter_id=encounter.id,
                doctor_role_id="therapist",
                doctor_name="Старое ФИО",
                fields_json={},
                is_completed=True,
                created_by_user_id=1,
            )
        )
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _directory_entry(self) -> CenterDoctorName:
        return self.db.execute(select(CenterDoctorName)).scalar_one()

    def test_update_persists_directory_and_refreshes_existing_exams(self) -> None:
        result = update_doctor_role(
            "therapist",
            DoctorRoleUpdate(full_name="  Иванов   Иван Иванович  "),
            self.center_id,
            self.db,
        )

        exam = self.db.execute(select(DoctorExam)).scalar_one()
        self.assertEqual(result.full_name, "Иванов Иван Иванович")
        self.assertEqual(self._directory_entry().full_name, "Иванов Иван Иванович")
        self.assertEqual(exam.doctor_name, "Иванов Иван Иванович")

    def test_clearing_directory_clears_existing_exam_name(self) -> None:
        update_doctor_role("therapist", DoctorRoleUpdate(full_name=""), self.center_id, self.db)

        exam = self.db.execute(select(DoctorExam)).scalar_one()
        self.assertIsNone(self._directory_entry().full_name)
        self.assertIsNone(exam.doctor_name)


if __name__ == "__main__":
    unittest.main()
