from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


os.environ.setdefault("ALLOW_SQLITE", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.v1.routes.doctor_roles import update_doctor_role  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.doctor_exam import DoctorExam  # noqa: E402
from app.models.service import DoctorRole  # noqa: E402
from app.schemas.doctor_role import DoctorRoleUpdate  # noqa: E402


class DoctorRoleDirectoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[Base.metadata.tables["doctor_roles"], Base.metadata.tables["doctor_exams"]],
        )
        self.db = Session(self.engine)
        self.db.add(DoctorRole(id=8, code="therapist", name="Терапевт", sort_order=8, is_active=True))
        self.db.add(
            DoctorExam(
                client_id=1,
                encounter_id=10,
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
        self.engine.dispose()

    def test_update_persists_directory_and_refreshes_existing_exams(self) -> None:
        result = update_doctor_role(
            "therapist",
            DoctorRoleUpdate(full_name="  Иванов   Иван Иванович  "),
            self.db,
        )

        exam = self.db.execute(select(DoctorExam)).scalar_one()
        self.assertEqual(result.full_name, "Иванов Иван Иванович")
        self.assertEqual(exam.doctor_name, "Иванов Иван Иванович")

    def test_clearing_directory_clears_existing_exam_name(self) -> None:
        update_doctor_role("therapist", DoctorRoleUpdate(full_name=""), self.db)

        role = self.db.execute(select(DoctorRole)).scalar_one()
        exam = self.db.execute(select(DoctorExam)).scalar_one()
        self.assertIsNone(role.full_name)
        self.assertIsNone(exam.doctor_name)


if __name__ == "__main__":
    unittest.main()
