from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.imports import (  # noqa: E402
    commit_client_excel_import,
    parse_optional_date,
    preview_client_excel_import,
    service_import_label,
    validate_client_import_rows,
)
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.models.encounter_service import EncounterService  # noqa: E402
from app.models.payment import Payment  # noqa: E402
from app.models.service import Service  # noqa: E402
from app.models.user import Role, User  # noqa: E402
from app.schemas.imports import ClientImportExcelRequest  # noqa: E402


class ClientExcelImportTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

        center = Center(id=1, code="center", name="Медцентр", is_active=True)
        role = Role(id=1, code="admin", name="Администратор")
        user = User(
            id=1,
            center_id=1,
            role_id=1,
            login="admin",
            password_hash="test",
            full_name="Администратор",
            is_active=True,
        )
        self.service = Service(
            id=1,
            code="service-pool",
            name="Справка в бассейн",
            price=Decimal("1000.00"),
            is_active=True,
        )
        self.db.add_all([center, role, user, self.service])
        self.db.commit()
        self.request = ClientImportExcelRequest(file_name="clients.xlsx", file_content_base64="")

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _row(self, **overrides):
        row = {
            "row_number": 2,
            "patient_number": None,
            "last_name": "Иванов",
            "first_name": "Иван",
            "middle_name": "Иванович",
            "birth_date": date(1990, 5, 20),
            "sex": "муж",
            "phone": "+79990000000",
            "snils": "111-222-333 44",
            "registration_text": "Санкт-Петербург",
            "organization": "ООО Тест",
            "service": service_import_label(self.service),
            "encounter_date": date(2026, 7, 29),
            "notes": "Тестовый импорт",
            "_birth_date_invalid": False,
            "_document_issued_date_invalid": False,
            "_encounter_date_invalid": False,
        }
        row.update(overrides)
        return row

    def test_parses_native_excel_date_serial_and_iso_datetime(self):
        self.assertEqual(parse_optional_date("43971"), date(2020, 5, 20))
        self.assertEqual(parse_optional_date("2026-07-29T12:30:00"), date(2026, 7, 29))

    def test_empty_file_and_missing_birth_date_have_clear_errors(self):
        with self.assertRaisesRegex(ValueError, "не найдено ни одной"):
            validate_client_import_rows([])

        with self.assertRaisesRegex(ValueError, "не заполнена дата рождения"):
            validate_client_import_rows([self._row(birth_date=None)])

    def test_commit_creates_client_encounter_service_and_payment(self):
        with patch(
            "app.api.v1.routes.imports.read_client_excel_rows",
            return_value=[self._row()],
        ):
            result = commit_client_excel_import(self.request, db=self.db)

        self.assertEqual(result.created, 1)
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.encounters_created, 1)
        self.assertEqual(self.db.scalar(select(func.count(Client.id))), 1)
        self.assertEqual(self.db.scalar(select(func.count(Encounter.id))), 1)
        self.assertEqual(self.db.scalar(select(func.count(EncounterService.id))), 1)
        self.assertEqual(self.db.scalar(select(func.count(Payment.id))), 1)

        client = self.db.execute(select(Client)).scalar_one()
        encounter = self.db.execute(select(Encounter)).scalar_one()
        encounter_service = self.db.execute(select(EncounterService)).scalar_one()
        payment = self.db.execute(select(Payment)).scalar_one()
        self.assertEqual(client.birth_date, date(1990, 5, 20))
        self.assertEqual(client.legacy_payload_json["birth_date"], "1990-05-20")
        self.assertEqual(client.encounter_date_text, "2026-07-29")
        self.assertEqual(encounter.client_id, client.id)
        self.assertEqual(encounter_service.service_id, self.service.id)
        self.assertEqual(payment.amount, Decimal("1000.00"))

    def test_preview_rejects_unknown_service(self):
        row = self._row(service="Несуществующая услуга")
        with patch(
            "app.api.v1.routes.imports.read_client_excel_rows",
            return_value=[row],
        ):
            with self.assertRaises(HTTPException) as error:
                preview_client_excel_import(self.request, db=self.db)

        self.assertEqual(error.exception.status_code, 400)
        self.assertIn("не найдена", str(error.exception.detail))


if __name__ == "__main__":
    unittest.main()
