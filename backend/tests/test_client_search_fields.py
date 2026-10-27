from pathlib import Path
import sys
import unittest
from datetime import date

from sqlalchemy import create_engine, or_, select
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.clients import client_search_conditions  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.blank_form import BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE, BlankBatch, BlankForm  # noqa: E402
from app.models.client import Client  # noqa: E402


class ClientSearchFieldsTests(unittest.TestCase):
    """Поиск по таблице клиентов ищет по ФИО, организации, агенту и номеру выданной справки."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.ivanov = Client(
            patient_number=101,
            last_name="Иванов",
            first_name="Пётр",
            birth_date=date(1980, 1, 2),
            organization="ООО РАДУГА",
            legacy_payload_json={"agent": "Сидорова"},
        )
        self.petrov = Client(patient_number=102, last_name="Петров", first_name="Анна", birth_date=date(1990, 3, 4))
        self.db.add_all([self.ivanov, self.petrov])
        self.db.flush()
        batch = BlankBatch(
            blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
            series="41",
            number_from=1,
            number_to=1,
            quantity=1,
        )
        self.db.add(batch)
        self.db.flush()
        self.db.add(
            BlankForm(
                batch_id=batch.id,
                blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                series="41",
                number_value=1,
                full_number="410000001",
                status="issued",
                client_id=self.petrov.id,
            )
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _found(self, value):
        conditions = client_search_conditions(value)
        query = select(Client.last_name).where(or_(*conditions))
        return sorted(row[0] for row in self.db.execute(query))

    def test_search_by_full_name_words(self):
        self.assertEqual(self._found("Иванов Пётр"), ["Иванов"])

    def test_search_by_organization(self):
        self.assertEqual(self._found("РАДУГА"), ["Иванов"])

    def test_search_by_agent_from_legacy_payload(self):
        self.assertEqual(self._found("Сидорова"), ["Иванов"])

    def test_search_by_issued_blank_number(self):
        self.assertEqual(self._found("410000001"), ["Петров"])

    def test_every_word_must_match_somewhere(self):
        self.assertEqual(self._found("Петров радуга"), [])


if __name__ == "__main__":
    unittest.main()
