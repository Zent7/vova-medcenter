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
    read_xlsx_rows,
    rows_to_client_records,
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
from app.models.visit_type import VisitType  # noqa: E402
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
        self.lmk_service = Service(
            id=2,
            legacy_source_id=18,
            code="service-lmk",
            name="ЛМК",
            price=Decimal("4000.00"),
            is_active=True,
        )
        self.lmk_visit_type = VisitType(
            id=1,
            code="lmk_new",
            name="ЛМК",
            is_active=True,
        )
        self.db.add_all([center, role, user, self.service, self.lmk_service, self.lmk_visit_type])
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

    def test_reads_customer_template_and_ignores_embedded_document_type_options(self):
        template_path = Path(__file__).resolve().parents[2] / "frontend" / "public" / "demo" / "client-import-template.xlsx"

        rows = read_xlsx_rows(template_path.read_bytes())

        self.assertEqual(rows, [])

    def test_maps_customer_columns_and_builds_registration_address(self):
        headers = [
            "Тип документа",
            "Фамилия",
            "Имя",
            "Отчество",
            "Дата рождения (формат 31.12.2026)",
            "Пол",
            "Адрес Регистрация-ОБЛОСТЬ",
            "Адрес Регистрация-ГОРОД",
            "Адрес Регистрация-УЛИЦА",
            "Адрес Регистрация-НОМЕР ДОМА",
            "корпус, литер, строение",
            "квартира",
            "Название Организация",
            "Должность",
            "Вредные произв. Факторы",
            "СНИЛС",
            "ФЛГ от ",
            "Примечание",
        ]
        values = [
            "ЛМК",
            "Петров",
            "Пётр",
            "Петрович",
            "20.05.1990",
            "муж",
            "Тверская область",
            "Тверь",
            "Лесная",
            "10",
            "2",
            "15",
            "ООО Завод",
            "Слесарь",
            "3.1, 4.2",
            "111-222-333 44",
            "01.08.2026",
            "Срочно",
        ]

        rows = rows_to_client_records([dict(enumerate(headers)), dict(enumerate(values))])

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["medical_document_type"], "ЛМК")
        self.assertNotIn("document_type", row)
        self.assertEqual(row["birth_date"], date(1990, 5, 20))
        self.assertEqual(
            row["registration_text"],
            "Тверская область, Тверь, Лесная, д. 10, корп./стр. 2, кв. 15",
        )
        self.assertEqual(row["profession"], "Слесарь")
        self.assertEqual(row["indications"], "3.1, 4.2")
        self.assertEqual(row["flg"], "01.08.2026")

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

    def test_document_type_automatically_creates_lmk_visit_with_all_client_fields(self):
        row = self._row(
            service=None,
            medical_document_type="ЛМК",
            organization="ООО Завод",
            profession="Слесарь",
            indications="3.1, 4.2",
            flg="01.08.2026",
            registration_text="Тверская область, Тверь, Лесная, д. 10",
        )
        with patch(
            "app.api.v1.routes.imports.read_client_excel_rows",
            return_value=[row],
        ):
            result = commit_client_excel_import(self.request, db=self.db)

        self.assertEqual(result.created, 1)
        self.assertEqual(result.encounters_created, 1)
        client = self.db.execute(select(Client)).scalar_one()
        encounter = self.db.execute(select(Encounter)).scalar_one()
        encounter_service = self.db.execute(select(EncounterService)).scalar_one()
        self.assertEqual(client.organization, "ООО Завод")
        self.assertEqual(client.work_place, "ООО Завод")
        self.assertEqual(client.profession, "Слесарь")
        self.assertEqual(client.indications, "3.1, 4.2")
        self.assertEqual(client.flg, "01.08.2026")
        self.assertEqual(client.address_text, "Тверская область, Тверь, Лесная, д. 10")
        self.assertEqual(encounter.visit_type_id, self.lmk_visit_type.id)
        self.assertEqual(encounter_service.service_id, self.lmk_service.id)


if __name__ == "__main__":
    unittest.main()
