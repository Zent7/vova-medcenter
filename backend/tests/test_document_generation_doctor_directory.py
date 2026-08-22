from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


os.environ.setdefault("ALLOW_SQLITE", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.base import Base  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.doctor_exam import DoctorExam  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.models.service import DoctorRole  # noqa: E402
from app.services.document_generator import _load_encounter_document_values  # noqa: E402


class DocumentGenerationDoctorDirectoryTests(unittest.TestCase):
    def test_generation_overrides_old_exam_name_with_current_directory(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            client = Client(
                patient_number=1,
                last_name="Тестов",
                first_name="Тест",
                birth_date=date(1990, 1, 1),
                created_by_user_id=1,
            )
            db.add(client)
            db.flush()
            center = Center(code="test", name="Тестовый центр", address="")
            db.add(center)
            db.flush()
            encounter = Encounter(
                center_id=center.id,
                client_id=client.id,
                encounter_date=date(2026, 8, 13),
                payment_type="cash",
                created_by_user_id=1,
            )
            db.add(encounter)
            db.flush()
            db.add(DoctorRole(id=8, code="therapist", name="Терапевт", full_name="Новое ФИО"))
            db.add(
                DoctorExam(
                    client_id=client.id,
                    encounter_id=encounter.id,
                    doctor_role_id="therapist",
                    doctor_name="Старое ФИО",
                    fields_json={},
                    is_completed=True,
                    created_by_user_id=1,
                )
            )
            db.commit()

            runtime_values = _load_encounter_document_values(db, client, encounter)

            self.assertEqual(runtime_values["doctor_name"], "Новое ФИО")
            self.assertEqual(runtime_values["exams"][0].doctor_name, "Новое ФИО")

        engine.dispose()


if __name__ == "__main__":
    unittest.main()
