from __future__ import annotations

from datetime import date
import os
import sys
import unittest
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


os.environ.setdefault("ALLOW_SQLITE", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.clients import create_client, update_client_notes  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.schemas.client import ClientCreate, ClientNotesUpdate  # noqa: E402


class ClientNotesUpdateTests(unittest.TestCase):
    """Примечание карточки меняется из окна обращения и не трогает остальные поля."""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        created = create_client(
            ClientCreate(
                last_name="Картов",
                first_name="Иван",
                birth_date=date(1985, 3, 4),
                sex="M",
                phone="+7 900 111-22-33",
                notes="Старое примечание",
            ),
            self.db,
        )
        self.client_id = created.id

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_note_is_replaced_and_other_fields_stay(self) -> None:
        saved = update_client_notes(self.client_id, ClientNotesUpdate(notes="  Новый комментарий  "), self.db)

        self.assertEqual(saved.notes, "Новый комментарий")
        self.assertEqual(saved.phone, "+7 900 111-22-33")
        self.assertEqual(saved.last_name, "Картов")
        self.assertEqual(saved.birth_date, date(1985, 3, 4))

    def test_blank_note_clears_the_note(self) -> None:
        saved = update_client_notes(self.client_id, ClientNotesUpdate(notes="   "), self.db)

        self.assertIsNone(saved.notes)

    def test_missing_client_is_not_found(self) -> None:
        with self.assertRaises(HTTPException) as context:
            update_client_notes(999999, ClientNotesUpdate(notes="x"), self.db)

        self.assertEqual(context.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
