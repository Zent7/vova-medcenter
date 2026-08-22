from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.payments import list_cash_report_rows  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.models.encounter_service import EncounterService  # noqa: E402
from app.models.payment import Payment  # noqa: E402
from app.models.service import Service  # noqa: E402


class CashReportRowsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.center_1 = Center(id=1, code="center-1", name="Медцентр 1")
        self.center_2 = Center(id=2, code="center-2", name="Медцентр 2")
        self.client = Client(
            id=1,
            patient_number=100,
            last_name="Иванов",
            first_name="Иван",
            middle_name="Иванович",
            birth_date=date(1990, 1, 1),
        )
        self.service = Service(
            id=1,
            code="driver",
            name="Справка водительская",
            price=Decimal("4000.00"),
            is_active=True,
        )
        self.db.add_all([self.center_1, self.center_2, self.client, self.service])
        self.db.flush()

        self.encounter = Encounter(
            id=1,
            center_id=self.center_1.id,
            client_id=self.client.id,
            encounter_date=date(2026, 8, 20),
            payment_type="cash",
            total_amount=Decimal("3500.00"),
            comment="Скидка",
            status="draft",
        )
        self.db.add(self.encounter)
        self.db.flush()
        self.db.add_all(
            [
                EncounterService(
                    encounter_id=self.encounter.id,
                    service_id=self.service.id,
                    quantity=1,
                    unit_price=Decimal("3500.00"),
                    line_total=Decimal("3500.00"),
                    notes='{"comment":"оплата наличными"}',
                ),
                Payment(
                    encounter_id=self.encounter.id,
                    payment_date=date(2026, 8, 20),
                    payment_type="cash",
                    amount=Decimal("3500.00"),
                    status="paid",
                    comment="Первичный платёж",
                ),
            ]
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_cash_report_returns_paid_rows_with_client_and_services(self):
        rows = list_cash_report_rows(
            date_from=date(2026, 8, 20),
            date_to=date(2026, 8, 20),
            center_id=self.center_1.id,
            db=self.db,
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.client_full_name, "Иванов Иван Иванович")
        self.assertEqual(row.center_name, "Медцентр 1")
        self.assertEqual(row.payment_type, "cash")
        self.assertEqual(row.amount, Decimal("3500.00"))
        self.assertEqual(row.discount, Decimal("500.00"))
        self.assertEqual(len(row.services), 1)
        self.assertEqual(row.services[0].name, "Справка водительская")
        self.assertEqual(row.services[0].paid_price, Decimal("3500.00"))
        self.assertEqual(row.services[0].comment, "оплата наличными")

    def test_cash_report_filters_by_center_and_date(self):
        self.assertEqual(
            list_cash_report_rows(
                date_from=date(2026, 8, 21),
                date_to=date(2026, 8, 21),
                center_id=self.center_1.id,
                db=self.db,
            ),
            [],
        )
        self.assertEqual(
            list_cash_report_rows(
                date_from=date(2026, 8, 20),
                date_to=date(2026, 8, 20),
                center_id=self.center_2.id,
                db=self.db,
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
