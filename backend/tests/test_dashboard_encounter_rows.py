from datetime import date, datetime
from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.dashboard import get_dashboard_encounter_rows  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.models.encounter_service import EncounterService  # noqa: E402
from app.models.service import Service  # noqa: E402


class DashboardEncounterRowsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(Center(id=1, code="demo", name="Demo"))
        self.db.add_all(
            [
                Client(
                    id=1,
                    patient_number=1,
                    last_name="Иванов",
                    first_name="Иван",
                    middle_name="Иванович",
                    birth_date=date(1990, 1, 1),
                    organization="Acme Clinic",
                    registration_text="Moscow",
                    created_at=datetime(2026, 1, 1, 8, 0),
                ),
                Client(
                    id=2,
                    patient_number=2,
                    last_name="Petrova",
                    first_name="Anna",
                    birth_date=date(1992, 2, 2),
                    organization="No Visit Org",
                    created_at=datetime(2026, 1, 2, 8, 0),
                ),
            ]
        )
        self.db.add_all(
            [
                Service(id=1, code="service-a", name="Service A", price=100),
                Service(id=2, code="service-b", name="Service B", price=200),
                Service(id=3, code="service-c", name="Service C", price=300),
            ]
        )
        self.db.flush()
        self.db.add_all(
            [
                Encounter(
                    id=10,
                    center_id=1,
                    client_id=1,
                    encounter_date=date(2026, 7, 1),
                    payment_type="cash",
                    total_amount=300,
                    status="closed",
                    comment="older multi-service",
                    created_at=datetime(2026, 7, 1, 9, 0),
                ),
                Encounter(
                    id=11,
                    center_id=1,
                    client_id=1,
                    encounter_date=date(2026, 7, 20),
                    payment_type="invoice",
                    total_amount=300,
                    status="draft",
                    comment="newer single-service",
                    created_at=datetime(2026, 7, 20, 10, 0),
                ),
                Encounter(
                    id=12,
                    center_id=1,
                    client_id=1,
                    encounter_date=date(2026, 7, 21),
                    payment_type="cash",
                    total_amount=100,
                    status="draft",
                    deleted_at=datetime(2026, 7, 21, 12, 0),
                    created_at=datetime(2026, 7, 21, 11, 0),
                ),
            ]
        )
        self.db.flush()
        self.db.add_all(
            [
                EncounterService(encounter_id=10, service_id=1, unit_price=100, line_total=100),
                EncounterService(encounter_id=10, service_id=2, unit_price=200, line_total=200),
                EncounterService(encounter_id=11, service_id=3, unit_price=300, line_total=300),
                EncounterService(encounter_id=12, service_id=1, unit_price=100, line_total=100),
            ]
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _rows(self, **overrides):
        params = {
            "search": None,
            "encounter_date": None,
            "encounter_date_from": None,
            "encounter_date_to": None,
            "limit": 100,
            "offset": 0,
            "db": self.db,
        }
        params.update(overrides)
        return get_dashboard_encounter_rows(**params)

    def test_returns_one_row_per_encounter_and_one_for_client_without_encounter(self):
        rows = self._rows()

        self.assertEqual([row.encounter_id for row in rows], [11, 10, None])
        self.assertEqual([row.client_id for row in rows], [1, 1, 2])
        self.assertEqual(rows[0].services, ["Service C"])
        self.assertEqual(rows[1].services, ["Service A", "Service B"])
        self.assertEqual(rows[2].services, [])
        self.assertEqual(rows[0].organization, "Acme Clinic")
        self.assertEqual(rows[0].encounter_date, date(2026, 7, 20))
        self.assertEqual(rows[0].center_name, "Demo")
        self.assertEqual(rows[0].latest_encounter_created_at, rows[0].encounter_created_at)

    def test_date_range_filters_encounters_and_excludes_empty_client_rows(self):
        rows = self._rows(
            encounter_date_from=date(2026, 7, 20),
            encounter_date_to=date(2026, 7, 20),
        )

        self.assertEqual([row.encounter_id for row in rows], [11])
        self.assertEqual(rows[0].services, ["Service C"])

    def test_exact_encounter_date_filter_is_supported(self):
        rows = self._rows(encounter_date=date(2026, 7, 1))

        self.assertEqual([row.encounter_id for row in rows], [10])

    def test_search_matches_client_fields_and_preserves_all_client_encounters(self):
        rows = self._rows(search="Acme Clinic")

        self.assertEqual([row.encounter_id for row in rows], [11, 10])
        self.assertTrue(all(row.birth_date == date(1990, 1, 1) for row in rows))

        client_without_encounter = self._rows(search="Petrova")
        self.assertEqual(len(client_without_encounter), 1)
        self.assertEqual(client_without_encounter[0].client_id, 2)
        self.assertIsNone(client_without_encounter[0].encounter_id)

        full_name_rows = self._rows(search="Иванов Иван Иванович")
        self.assertEqual([row.encounter_id for row in full_name_rows], [11, 10])

    def test_limit_and_offset_are_applied_to_journal_rows(self):
        rows = self._rows(limit=1, offset=1)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].encounter_id, 10)


if __name__ == "__main__":
    unittest.main()
