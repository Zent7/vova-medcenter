from datetime import date
from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.doctor_exams import (  # noqa: E402
    create_or_update_doctor_exam,
    update_doctor_exam,
)
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.doctor_exam import DoctorExam  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.schemas.doctor_exam import DoctorExamCreate, DoctorExamUpdate  # noqa: E402


class DoctorExamSyncKeepsCompletedTests(unittest.TestCase):
    """Браузер досылает локальные карточки врачей при сохранении обращения и перед
    печатью. Черновик не должен снимать закрытие осмотра: иначе врач в выписке
    профа и в амбулаторной карте остаётся без даты и заключения."""

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
                encounter_date=date(2026, 10, 5),
                payment_type="cash",
                total_amount=0,
                status="draft",
            )
        )
        self.db.add(
            DoctorExam(
                id=1,
                client_id=1,
                encounter_id=1,
                doctor_role_id="therapist",
                doctor_name="Терапевт",
                result_text="Противопоказаний не выявлено",
                fields_json={"conclusion": "Противопоказаний не выявлено"},
                is_completed=True,
                completed_at=None,
            )
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _payload(self, **overrides):
        data = {
            "client_id": 1,
            "encounter_id": 1,
            "doctor_role_id": "therapist",
            "doctor_name": "Казаков И.В.",
            "fields_json": {},
            "is_completed": False,
        }
        data.update(overrides)
        return DoctorExamCreate(**data)

    def _exams(self):
        return self.db.execute(select(DoctorExam)).scalars().all()

    def test_draft_from_browser_does_not_reopen_completed_exam(self):
        saved = create_or_update_doctor_exam(self._payload(), self.db)

        self.assertTrue(saved.is_completed)
        exam = self._exams()[0]
        self.assertTrue(exam.is_completed)
        self.assertIsNotNone(exam.completed_at)
        self.assertEqual(exam.fields_json, {"conclusion": "Противопоказаний не выявлено"})
        self.assertEqual(exam.result_text, "Противопоказаний не выявлено")

    def test_draft_from_browser_still_refreshes_doctor_name(self):
        create_or_update_doctor_exam(self._payload(doctor_name="Казаков И.В."), self.db)

        self.assertEqual(self._exams()[0].doctor_name, "Казаков И.В.")
        self.assertEqual(len(self._exams()), 1)

    def test_saving_the_card_still_completes_and_updates_the_exam(self):
        saved = create_or_update_doctor_exam(
            self._payload(fields_json={"conclusion": "Годен"}, is_completed=True), self.db
        )

        self.assertTrue(saved.is_completed)
        self.assertEqual(self._exams()[0].fields_json, {"conclusion": "Годен"})

    def test_draft_still_updates_a_draft_exam(self):
        exam = self._exams()[0]
        exam.is_completed = False
        self.db.commit()

        create_or_update_doctor_exam(self._payload(fields_json={"complaints": "нет"}), self.db)

        refreshed = self._exams()[0]
        self.assertFalse(refreshed.is_completed)
        self.assertEqual(refreshed.fields_json, {"complaints": "нет"})

    def test_explicit_uncomplete_through_put_still_works(self):
        saved = update_doctor_exam(1, DoctorExamUpdate(is_completed=False), self.db)

        self.assertFalse(saved.is_completed)
        self.assertFalse(self._exams()[0].is_completed)
        self.assertIsNone(self._exams()[0].completed_at)


if __name__ == "__main__":
    unittest.main()
