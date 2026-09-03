"""Врачи заводятся отдельно в каждом медцентре.

Раньше ФИО врача лежало в `doctor_roles.full_name` — одной строкой на всю базу.
Второй медцентр не мог назначить своего терапевта, не переписав терапевта
первому, а документ подписывался чужим врачом.
"""

from datetime import date
from pathlib import Path
import os
import sys
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker


os.environ.setdefault("ALLOW_SQLITE", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.doctor_roles import list_doctor_roles, update_doctor_role  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.center_doctor_name import CenterDoctorName  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.doctor_exam import DoctorExam  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.models.service import DoctorRole  # noqa: E402
from app.schemas.doctor_role import DoctorRoleUpdate  # noqa: E402
from app.services.doctor_directory import get_center_doctor_names, set_center_doctor_name  # noqa: E402
from app.services.document_generator import _load_encounter_document_values  # noqa: E402


class CenterDoctorDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

        with self.Session() as db:
            db.add_all(
                [
                    Center(code="center-a", name="Медцентр 1"),
                    Center(code="center-b", name="Медцентр 2"),
                    DoctorRole(id=1, code="therapist", name="Терапевт", sort_order=10),
                    DoctorRole(id=2, code="surgeon", name="Хирург", sort_order=20),
                ]
            )
            db.commit()
            self.first = self._center_id(db, "center-a")
            self.second = self._center_id(db, "center-b")

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _center_id(self, db: Session, code: str) -> int:
        return db.execute(select(Center.id).where(Center.code == code)).scalar_one()

    def _save_name(self, center_id: int, role_code: str, full_name: str | None):
        with self.Session() as db:
            return update_doctor_role(
                role_code=role_code,
                payload=DoctorRoleUpdate(full_name=full_name),
                center_id=center_id,
                db=db,
            )

    def _read_names(self, center_id: int | None) -> dict[str, str | None]:
        with self.Session() as db:
            return {role.code: role.full_name for role in list_doctor_roles(center_id=center_id, db=db)}

    def test_name_saved_in_one_center_does_not_reach_another(self):
        saved = self._save_name(self.first, "therapist", "Казаков И.В.")

        self.assertEqual(saved.full_name, "Казаков И.В.")
        self.assertEqual(
            self._read_names(self.first), {"therapist": "Казаков И.В.", "surgeon": None}
        )
        self.assertEqual(self._read_names(self.second), {"therapist": None, "surgeon": None})

    def test_each_center_keeps_its_own_doctor_for_the_same_specialty(self):
        self._save_name(self.first, "therapist", "Первый врач")
        self._save_name(self.second, "therapist", "Второй врач")

        with self.Session() as db:
            self.assertEqual(get_center_doctor_names(db, self.first)["therapist"], "Первый врач")
            self.assertEqual(get_center_doctor_names(db, self.second)["therapist"], "Второй врач")

    def test_directory_without_a_center_stays_empty(self):
        self._save_name(self.first, "therapist", "Казаков И.В.")

        self.assertEqual(self._read_names(None), {"therapist": None, "surgeon": None})

    def test_saving_a_name_renames_only_this_center_exams(self):
        with self.Session() as db:
            client = Client(
                patient_number=1,
                last_name="Тестов",
                first_name="Тест",
                birth_date=date(1990, 1, 1),
                created_by_user_id=1,
            )
            db.add(client)
            db.flush()
            for center_id, doctor in ((self.first, "Врач первого"), (self.second, "Врач второго")):
                encounter = Encounter(
                    center_id=center_id,
                    client_id=client.id,
                    encounter_date=date(2026, 9, 1),
                    payment_type="cash",
                    created_by_user_id=1,
                )
                db.add(encounter)
                db.flush()
                db.add(
                    DoctorExam(
                        client_id=client.id,
                        encounter_id=encounter.id,
                        doctor_role_id="therapist",
                        doctor_name=doctor,
                        fields_json={},
                        is_completed=True,
                        created_by_user_id=1,
                    )
                )
            db.commit()

        self._save_name(self.first, "therapist", "Новый врач")

        with self.Session() as db:
            names_by_center = {
                encounter.center_id: exam.doctor_name
                for exam, encounter in db.execute(
                    select(DoctorExam, Encounter).join(Encounter, Encounter.id == DoctorExam.encounter_id)
                ).all()
            }
            self.assertEqual(names_by_center[self.first], "Новый врач")
            self.assertEqual(names_by_center[self.second], "Врач второго")

    def test_generated_document_is_signed_by_the_encounter_center_doctor(self):
        with self.Session() as db:
            set_center_doctor_name(db, self.first, "therapist", "Врач первого")
            set_center_doctor_name(db, self.second, "therapist", "Врач второго")
            client = Client(
                patient_number=2,
                last_name="Тестов",
                first_name="Тест",
                birth_date=date(1990, 1, 1),
                created_by_user_id=1,
            )
            db.add(client)
            db.flush()
            encounter = Encounter(
                center_id=self.second,
                client_id=client.id,
                encounter_date=date(2026, 9, 1),
                payment_type="cash",
                created_by_user_id=1,
            )
            db.add(encounter)
            db.flush()
            db.add(
                DoctorExam(
                    client_id=client.id,
                    encounter_id=encounter.id,
                    doctor_role_id="therapist",
                    doctor_name="Устаревшее ФИО",
                    fields_json={},
                    is_completed=True,
                    created_by_user_id=1,
                )
            )
            db.commit()

            runtime_values = _load_encounter_document_values(db, client, encounter)

            self.assertEqual(runtime_values["doctor_name"], "Врач второго")
            self.assertEqual(runtime_values["exams"][0].doctor_name, "Врач второго")

    def test_clearing_a_name_removes_it_only_for_this_center(self):
        self._save_name(self.first, "therapist", "Казаков И.В.")
        cleared = self._save_name(self.first, "therapist", "   ")

        self.assertIsNone(cleared.full_name)
        with self.Session() as db:
            self.assertEqual(get_center_doctor_names(db, self.first), {})
            entry = db.execute(
                select(CenterDoctorName).where(CenterDoctorName.center_id == self.first)
            ).scalar_one()
            self.assertIsNone(entry.full_name)

    def test_unknown_center_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            self._save_name(9999, "therapist", "Кто-то")

        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
