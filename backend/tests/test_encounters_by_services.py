from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.encounters import create_encounters_by_services  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.models.encounter_service import EncounterService  # noqa: E402
from app.models.payment import Payment  # noqa: E402
from app.models.service import Service  # noqa: E402
from app.schemas.encounter import EncounterByServiceItemCreate, EncountersByServicesCreate  # noqa: E402


class EncountersByServicesTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.center = Center(id=1, code="center", name="Медцентр")
        self.client = Client(
            id=1,
            patient_number=1,
            last_name="Иванов",
            first_name="Иван",
            middle_name="Иванович",
            birth_date=date(1990, 1, 1),
            organization="ООО Тест",
        )
        self.services = [
            Service(
                id=index,
                code=f"service-{index}",
                name=f"Услуга {index}",
                price=Decimal(f"{index}00.00"),
                is_active=True,
            )
            for index in range(1, 6)
        ]
        self.db.add_all([self.center, self.client, *self.services])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _payload(self, service_count: int) -> EncountersByServicesCreate:
        return EncountersByServicesCreate(
            center_id=self.center.id,
            client_id=self.client.id,
            encounter_date=date(2026, 7, 21),
            services=[
                EncounterByServiceItemCreate(
                    service_id=service.id,
                    payment_type="cash" if index % 2 else "card",
                    comment=f"Оплата услуги {service.id}",
                    notes=f'{{"serviceId": {service.id}}}',
                )
                for index, service in enumerate(self.services[:service_count], start=1)
            ],
        )

    def _assert_created(self, service_count: int) -> None:
        response = create_encounters_by_services(self._payload(service_count), db=self.db)

        encounters = self.db.execute(select(Encounter).order_by(Encounter.id.asc())).scalars().all()
        encounter_services = self.db.execute(
            select(EncounterService).order_by(EncounterService.encounter_id.asc())
        ).scalars().all()
        payments = self.db.execute(select(Payment).order_by(Payment.encounter_id.asc())).scalars().all()

        self.assertEqual(len(response), service_count)
        self.assertEqual(len(encounters), service_count)
        self.assertEqual(len(encounter_services), service_count)
        self.assertEqual(len(payments), service_count)
        self.assertEqual(self.db.scalar(select(func.count(Client.id))), 1)
        self.assertEqual({item.service_id for item in encounter_services}, set(range(1, service_count + 1)))

        services_by_encounter = {item.encounter_id: item for item in encounter_services}
        payments_by_encounter = {item.encounter_id: item for item in payments}
        for encounter in encounters:
            self.assertEqual(encounter.client_id, self.client.id)
            self.assertIn(encounter.id, services_by_encounter)
            self.assertIn(encounter.id, payments_by_encounter)
            service_item = services_by_encounter[encounter.id]
            payment = payments_by_encounter[encounter.id]
            self.assertEqual(service_item.quantity, 1)
            self.assertEqual(service_item.unit_price, encounter.total_amount)
            self.assertEqual(service_item.line_total, encounter.total_amount)
            self.assertEqual(payment.amount, encounter.total_amount)
            self.assertEqual(payment.payment_type, encounter.payment_type)
            self.assertEqual(payment.comment, encounter.comment)

        self.db.refresh(self.client)
        self.assertEqual(self.client.birth_date, date(1990, 1, 1))
        self.assertEqual(self.client.organization, "ООО Тест")
        self.assertIsNone(self.client.encounter_date_text)

    def test_creates_two_encounters_for_two_services_without_duplicating_client(self):
        self._assert_created(2)

    def test_creates_five_encounters_for_five_services_without_duplicating_client(self):
        self._assert_created(5)

    def test_invalid_service_rolls_back_entire_request(self):
        payload = EncountersByServicesCreate(
            center_id=self.center.id,
            client_id=self.client.id,
            encounter_date=date(2026, 7, 21),
            services=[
                EncounterByServiceItemCreate(service_id=self.services[0].id),
                EncounterByServiceItemCreate(service_id=999_999),
            ],
        )

        with self.assertRaises(HTTPException) as error:
            create_encounters_by_services(payload, db=self.db)

        self.assertEqual(error.exception.status_code, 404)
        self.assertIn("999999", str(error.exception.detail))
        self.assertEqual(self.db.scalar(select(func.count(Encounter.id))), 0)
        self.assertEqual(self.db.scalar(select(func.count(EncounterService.id))), 0)
        self.assertEqual(self.db.scalar(select(func.count(Payment.id))), 0)
        self.assertEqual(self.db.scalar(select(func.count(AuditLog.id))), 0)
        self.assertEqual(self.db.scalar(select(func.count(Client.id))), 1)


if __name__ == "__main__":
    unittest.main()
