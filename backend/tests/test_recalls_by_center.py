"""Повторы к обзвону принадлежат медцентру обращения.

Без фильтра «Календарь» третьего медцентра показывал пациентов первого, и
регистратор звал бы человека на повтор в чужой центр.
"""

from datetime import date, timedelta
from pathlib import Path
import os
import sys
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker


os.environ.setdefault("ALLOW_SQLITE", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.recalls import list_due_recalls  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.models.encounter_service import EncounterService  # noqa: E402
from app.models.service import Service  # noqa: E402


class RecallsByCenterTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

        with self.Session() as db:
            first = Center(code="center-a", name="Медцентр 1")
            second = Center(code="center-b", name="Медцентр 2")
            service = Service(code="med-inspection", name="Медосмотр", price=100, recall_after_days=365)
            db.add_all([first, second, service])
            db.flush()
            self.first = first.id
            self.second = second.id

            for center_id, last_name in ((first.id, "Первов"), (second.id, "Второв")):
                client = Client(
                    patient_number=center_id,
                    last_name=last_name,
                    first_name="Тест",
                    birth_date=date(1990, 1, 1),
                    created_by_user_id=1,
                )
                db.add(client)
                db.flush()
                encounter = Encounter(
                    center_id=center_id,
                    client_id=client.id,
                    # Год назад: повтор уже наступил и попадает в горизонт.
                    encounter_date=date.today() - timedelta(days=365),
                    payment_type="cash",
                    created_by_user_id=1,
                )
                db.add(encounter)
                db.flush()
                db.add(
                    EncounterService(
                        encounter_id=encounter.id,
                        service_id=service.id,
                        quantity=1,
                        unit_price=100,
                    )
                )
            db.commit()

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _due_last_names(self, center_id: int | None) -> set[str]:
        with self.Session() as db:
            rows = list_due_recalls(horizon_days=45, include_done=True, center_id=center_id, db=db)
            clients_by_id = {
                client.id: client.last_name
                for client in db.execute(select(Client)).scalars().all()
            }
            return {clients_by_id[row.client_id] for row in rows}

    def test_each_center_sees_only_its_own_recalls(self):
        self.assertEqual(self._due_last_names(self.first), {"Первов"})
        self.assertEqual(self._due_last_names(self.second), {"Второв"})

    def test_without_a_center_every_recall_is_returned(self):
        self.assertEqual(self._due_last_names(None), {"Первов", "Второв"})


if __name__ == "__main__":
    unittest.main()
