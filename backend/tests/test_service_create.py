from __future__ import annotations

import os
import sys
import unittest
from decimal import Decimal
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


os.environ.setdefault("ALLOW_SQLITE", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.services import create_service, list_services  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.service import DoctorRole, Service, ServiceCategory, ServiceDoctorRole  # noqa: E402
from app.schemas.service import ServiceCreate  # noqa: E402


class ServiceCreateTests(unittest.TestCase):
    """Новая услуга из раздела «Услуги» сохраняется в базе вместе с врачами."""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(ServiceCategory(id=1, code="certificates", name="Справки", sort_order=1))
        self.db.add(DoctorRole(id=8, code="therapist", name="Терапевт", sort_order=8, is_active=True))
        self.db.add(DoctorRole(id=9, code="ophthalmologist", name="Офтальмолог", sort_order=9, is_active=True))
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_create_persists_service_and_doctor_roles(self) -> None:
        result = create_service(
            ServiceCreate(
                category_id=1,
                name="  Справка для бассейна  ",
                price=Decimal("500"),
                recall_after_days=365,
                doctor_role_ids=[8, 9, 8],
            ),
            self.db,
        )

        service = self.db.get(Service, result.id)
        self.assertIsNotNone(service)
        self.assertEqual(service.name, "Справка для бассейна")
        self.assertTrue(service.code.startswith("custom-"))
        self.assertEqual(result.doctor_role_ids, [8, 9])
        role_ids = self.db.execute(
            select(ServiceDoctorRole.doctor_role_id).where(ServiceDoctorRole.service_id == service.id)
        ).scalars().all()
        self.assertEqual(sorted(role_ids), [8, 9])

        listed = {item.id: item for item in list_services(self.db)}
        self.assertEqual(sorted(listed[result.id].doctor_role_ids), [8, 9])

    def test_each_created_service_gets_unique_code(self) -> None:
        first = create_service(ServiceCreate(category_id=1, name="Услуга"), self.db)
        second = create_service(ServiceCreate(category_id=1, name="Услуга"), self.db)

        self.assertNotEqual(first.code, second.code)

    def test_blank_name_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            create_service(ServiceCreate(category_id=1, name="   "), self.db)

        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(self.db.execute(select(Service)).scalars().all(), [])


if __name__ == "__main__":
    unittest.main()
