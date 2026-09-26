from __future__ import annotations

from datetime import date
import os
import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


os.environ.setdefault("ALLOW_SQLITE", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.clients import create_client, update_client  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.schemas.client import ClientCreate, ClientUpdate  # noqa: E402


# Тело, которое карточка «Изменить клиента» отправляет при сохранении.
CARD_FIELDS = dict(
    last_name="Картов",
    first_name="Иван",
    middle_name="Петрович",
    birth_date=date(1985, 3, 4),
    citizenship=None,
    arrival_country=None,
    sex="M",
    phone="+7 900 111-22-33",
    email=None,
    document_type="Паспорт РФ",
    document_series=None,
    document_number=None,
    document_issued_by=None,
    document_issued_date=None,
    snils=None,
    oms_policy="7850123456789012",
    address_text=None,
    profession=None,
    work_place=None,
    organization=None,
    encounter_date_text="26.09.2026 11:00",
    notes=None,
    registration_text=None,
    legacy_payload_json={"source": "demo-client-modal", "services": [], "agent": "Агент-1"},
)


class ClientUpdateKeepsFieldsTests(unittest.TestCase):
    """Сохранение карточки клиента не стирает поля, которых в ней нет."""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        created = create_client(
            ClientCreate(
                last_name="Картов",
                first_name="Иван",
                middle_name="Петрович",
                birth_date=date(1985, 3, 4),
                card_number="0012345",
                mkb10="Z02.1",
                doctor_therapist="Казаков И.В.",
                admission_category="B",
                reference_number="REF-1",
                indications="Очки",
                oms_policy="7850123456789012",
                legacy_payload_json={"WhoGive": "ОВД Центрального района", "agent": "Агент-0"},
            ),
            self.db,
        )
        self.client_id = created.id

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def stored(self) -> Client:
        self.db.expire_all()
        return self.db.get(Client, self.client_id)

    def test_card_save_keeps_the_fields_it_does_not_send(self) -> None:
        update_client(self.client_id, ClientUpdate(**CARD_FIELDS), self.db)

        client = self.stored()
        self.assertEqual(client.phone, "+7 900 111-22-33")
        self.assertEqual(
            (
                client.card_number,
                client.mkb10,
                client.doctor_therapist,
                client.admission_category,
                client.reference_number,
                client.indications,
            ),
            ("0012345", "Z02.1", "Казаков И.В.", "B", "REF-1", "Очки"),
        )
        self.assertEqual(
            client.legacy_payload_json,
            {
                "WhoGive": "ОВД Центрального района",
                "agent": "Агент-1",
                "source": "demo-client-modal",
                "services": [],
            },
        )

    def test_explicit_null_clears_a_field_but_not_the_legacy_payload(self) -> None:
        update_client(
            self.client_id,
            ClientUpdate(**{**CARD_FIELDS, "mkb10": None, "legacy_payload_json": None}),
            self.db,
        )

        client = self.stored()
        self.assertIsNone(client.mkb10)
        self.assertEqual(client.card_number, "0012345")
        self.assertEqual(client.legacy_payload_json["WhoGive"], "ОВД Центрального района")


if __name__ == "__main__":
    unittest.main()
