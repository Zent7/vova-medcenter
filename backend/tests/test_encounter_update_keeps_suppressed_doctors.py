from datetime import date
from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.doctor_exams import delete_doctor_exam  # noqa: E402
from app.api.v1.routes.encounters import update_encounter  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.doctor_exam import DoctorExam  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.models.encounter_service import EncounterService  # noqa: E402
from app.models.service import DoctorRole, Service, ServiceDoctorRole  # noqa: E402
from app.schemas.encounter import EncounterUpdate  # noqa: E402
from app.services.medical_autofill import autofill_completed_doctors_for_service  # noqa: E402


class EncounterUpdateKeepsSuppressedDoctorsTests(unittest.TestCase):
    """Врач, удалённый в карточке осмотра, не возвращается при следующей синхронизации.

    Браузер при каждом сохранении обращения присылает свой список снятых врачей.
    Список, который отстал (гонка с удалением или устаревшая вкладка), не должен
    снимать исключение: иначе повторное автозаполнение услуги вернёт врача закрытым
    в амбулаторную карту и выписку профа."""

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
                encounter_date=date(2026, 10, 20),
                payment_type="cash",
                total_amount=0,
                status="draft",
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
        self.db.add(EncounterService(encounter_id=1, service_id=1, quantity=1, unit_price=100, line_total=100))
        self.db.commit()
        autofill_completed_doctors_for_service(self.db, self.db.get(Encounter, 1), 1)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _live_exams(self, role_code):
        return (
            self.db.execute(
                select(DoctorExam).where(
                    DoctorExam.encounter_id == 1,
                    DoctorExam.doctor_role_id == role_code,
                    DoctorExam.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )

    def _delete_therapist(self):
        exam = self._live_exams("therapist")[0]
        delete_doctor_exam(exam.id, self.db)
        self.assertEqual(self._live_exams("therapist"), [])

    def _resync_services(self):
        # Так синхронизация обращения пересоздаёт услуги: автозаполнение идёт заново.
        autofill_completed_doctors_for_service(self.db, self.db.get(Encounter, 1), 1)
        self.db.commit()

    def test_stale_suppression_list_does_not_bring_deleted_doctor_back(self):
        self._delete_therapist()

        update_encounter(1, EncounterUpdate(suppressed_doctor_role_ids=[]), self.db)
        self._resync_services()

        self.assertEqual(self.db.get(Encounter, 1).suppressed_doctor_role_ids, ["therapist"])
        self.assertEqual(self._live_exams("therapist"), [])
        self.assertEqual(len(self._live_exams("surgeon")), 1)

    def test_saving_keeps_already_suppressed_doctor_and_adds_new_ones(self):
        self._delete_therapist()

        update_encounter(1, EncounterUpdate(suppressed_doctor_role_ids=["surgeon"]), self.db)

        self.assertEqual(
            self.db.get(Encounter, 1).suppressed_doctor_role_ids,
            ["surgeon", "therapist"],
        )

    def test_doctor_exam_save_still_restores_suppressed_doctor(self):
        from app.api.v1.routes.doctor_exams import create_or_update_doctor_exam
        from app.schemas.doctor_exam import DoctorExamCreate

        self._delete_therapist()
        create_or_update_doctor_exam(
            DoctorExamCreate(
                client_id=1,
                encounter_id=1,
                doctor_role_id="therapist",
                doctor_name="Терапевт",
                fields_json={},
                is_completed=True,
            ),
            self.db,
        )

        self.assertEqual(self.db.get(Encounter, 1).suppressed_doctor_role_ids, [])
        self.assertEqual(len(self._live_exams("therapist")), 1)


if __name__ == "__main__":
    unittest.main()
