from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

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

    def test_unknown_service_warns_but_still_imports_client(self):
        row = self._row(service="Несуществующая услуга")
        with patch(
            "app.api.v1.routes.imports.read_client_excel_rows",
            return_value=[row],
        ):
            preview = preview_client_excel_import(self.request, db=self.db)
            result = commit_client_excel_import(self.request, db=self.db)

        self.assertEqual(preview.service_rows, 0)
        self.assertIn("не найдена", " ".join(preview.service_warnings))
        self.assertEqual(result.created, 1)
        self.assertEqual(result.encounters_created, 0)
        self.assertIn("не найдена", " ".join(result.service_warnings))
        self.assertEqual(self.db.scalar(select(func.count(Client.id))), 1)

    def test_deleted_client_is_not_matched_and_stays_deleted(self):
        deleted = Client(
            patient_number=9,
            last_name="Удалённый",
            first_name="Клиент",
            birth_date=date(1990, 5, 20),
            snils="999-888-777 66",
            deleted_at=datetime(2026, 1, 1),
        )
        self.db.add(deleted)
        self.db.commit()

        row = self._row(snils="999-888-777 66", service=None)
        with patch(
            "app.api.v1.routes.imports.read_client_excel_rows",
            return_value=[row],
        ):
            result = commit_client_excel_import(self.request, db=self.db)

        self.assertEqual(result.created, 1)
        self.assertEqual(result.updated, 0)
        self.db.refresh(deleted)
        self.assertIsNotNone(deleted.deleted_at)
        self.assertEqual(deleted.last_name, "Удалённый")

    def test_service_warning_rows_counts_every_row_not_only_shown(self):
        rows = [
            self._row(row_number=number, service="Несуществующая услуга")
            for number in range(2, 27)
        ]
        with patch(
            "app.api.v1.routes.imports.read_client_excel_rows",
            return_value=rows,
        ):
            preview = preview_client_excel_import(self.request, db=self.db)

        self.assertEqual(preview.service_warning_rows, 25)
        self.assertEqual(len(preview.service_warnings), 20)

    def test_update_keeps_fields_missing_from_template(self):
        existing = Client(
            patient_number=7,
            last_name="Иванов",
            first_name="Иван",
            middle_name="Иванович",
            birth_date=date(1990, 5, 20),
            snils="111-222-333 44",
            document_type="Паспорт РФ",
            document_series="4501",
            document_number="123456",
            document_issued_by="ГУ МВД России",
            email="ivanov@example.com",
            address_text="Тверь, Лесная 1",
            admission_category="Медкомиссия",
            reference_number="МК-001",
        )
        self.db.add(existing)
        self.db.commit()

        # Шаблон для завода не содержит паспортных колонок вовсе.
        narrow_row = {
            "row_number": 2,
            "patient_number": None,
            "last_name": "Иванов",
            "first_name": "Иван",
            "middle_name": "Иванович",
            "birth_date": date(1990, 5, 20),
            "snils": "111-222-333 44",
            "organization": "ООО Новый Завод",
            "_birth_date_invalid": False,
        }
        with patch(
            "app.api.v1.routes.imports.read_client_excel_rows",
            return_value=[narrow_row],
        ):
            result = commit_client_excel_import(self.request, db=self.db)

        self.assertEqual(result.updated, 1)
        self.assertEqual(result.created, 0)
        client = self.db.execute(select(Client)).scalar_one()
        self.assertEqual(client.organization, "ООО Новый Завод")
        self.assertEqual(client.document_series, "4501")
        self.assertEqual(client.document_number, "123456")
        self.assertEqual(client.document_type, "Паспорт РФ")
        self.assertEqual(client.email, "ivanov@example.com")
        self.assertEqual(client.address_text, "Тверь, Лесная 1")
        self.assertEqual(client.admission_category, "Медкомиссия")
        self.assertEqual(client.reference_number, "МК-001")


if __name__ == "__main__":
    unittest.main()
