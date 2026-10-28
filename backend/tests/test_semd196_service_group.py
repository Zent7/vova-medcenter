from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


os.environ.setdefault("ALLOW_SQLITE", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.models.service import Service, ServiceCategory  # noqa: E402
from app.services.seed import _ensure_service_catalog  # noqa: E402


class Semd196ServiceGroupTests(unittest.TestCase):
    """СЭМД-196 живёт в «Справках», даже если её завели в группу «ВУ»."""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        _ensure_service_catalog(self.db)
        self.driver_category = self.db.scalar(select(ServiceCategory).where(ServiceCategory.code == "legacy-group-2"))
        self.certificates_category = self.db.scalar(select(ServiceCategory).where(ServiceCategory.code == "legacy-group-7"))

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_manually_added_semd_service_returns_to_certificates(self) -> None:
        service = Service(code="custom-semd-manual", name="Справка по форме СЭМД-196 без ФЛГ", price=2500, category_id=self.driver_category.id)
        self.db.add(service)
        self.db.commit()

        _ensure_service_catalog(self.db)

        self.db.refresh(service)
        self.assertEqual(service.category_id, self.certificates_category.id)

    def test_legacy_semd_service_moved_to_driver_group_returns_to_certificates(self) -> None:
        service = self.db.scalar(select(Service).where(Service.legacy_source_id == 43))
        service.category_id = self.driver_category.id
        self.db.commit()

        _ensure_service_catalog(self.db)

        self.db.refresh(service)
        self.assertEqual(service.category_id, self.certificates_category.id)

    def test_driver_group_keeps_its_own_services(self) -> None:
        _ensure_service_catalog(self.db)

        driver_names = sorted(
            self.db.scalars(select(Service.name).where(Service.category_id == self.driver_category.id)).all()
        )
        self.assertEqual(driver_names, ["071У", "Медицинская комиссия", "Медицинская комиссия"])
        for name in driver_names:
            self.assertNotIn("сэмд", name.lower())


if __name__ == "__main__":
    unittest.main()
