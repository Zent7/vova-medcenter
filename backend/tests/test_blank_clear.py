from datetime import date, datetime
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.blanks import require_blank_clear_access  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.blank_form import (  # noqa: E402
    BLANK_STATUS_FREE,
    BLANK_STATUS_ISSUED,
    BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
    BlankForm,
    BlankType,
)
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.client_document import ClientDocument  # noqa: E402
from app.models.document_template import DocumentTemplate  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.models.generated_document import GeneratedDocument  # noqa: E402
from app.models.user import Role, User  # noqa: E402
from app.services.blank_forms import (  # noqa: E402
    clear_center_blanks,
    create_auto_number_form,
    create_batch,
    list_batches,
    stats,
)


class BlankClearTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")

        # SQLite по умолчанию не проверяет внешние ключи, а PostgreSQL проверяет:
        # без этого тест не заметил бы номер, удалённый из-под документа.
        @event.listens_for(self.engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        # drop_all со включёнными внешними ключами упирается во взаимные ссылки
        # blank_forms и generated_documents; база в памяти исчезнет и так.
        self.engine.dispose()

    def _seed(self, db):
        db.add(BlankType(code=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE, name="Водительская", is_active=True))
        role = Role(code="chairman", name="Председатель")
        db.add(role)
        db.flush()
        # Журнал аудита ссылается на пользователя 1, когда автор не передан.
        db.add(User(id=1, role_id=role.id, login="chairman", password_hash="-", full_name="Председатель"))
        first = Center(code="first", name="Медцентр 1")
        second = Center(code="second", name="Медцентр 2")
        client = Client(patient_number=1, last_name="Иванов", first_name="Иван", birth_date=date(1980, 1, 1))
        template = DocumentTemplate(
            code="clear_test",
            name="Водительская справка",
            template_type="docx",
            file_name="template.docx",
            file_path="template.docx",
            output_format="docx",
            is_active=True,
        )
        db.add_all([first, second, client, template])
        db.flush()

        for center in (first, second):
            create_batch(
                db,
                blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                series="40",
                number_from_input="1",
                number_to_input="5",
                received_at=None,
                comment=None,
                center_id=center.id,
                user_id=None,
            )
        create_auto_number_form(
            db,
            blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
            center_id=first.id,
            series="086У",
        )
        create_auto_number_form(
            db,
            blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
            center_id=first.id,
            series="086У",
        )

        encounter = Encounter(
            center_id=first.id,
            client_id=client.id,
            encounter_date=date(2026, 9, 1),
            payment_type="cash",
        )
        db.add(encounter)
        db.flush()

        issued = db.execute(
            select(BlankForm).where(BlankForm.center_id == first.id, BlankForm.series == "40").limit(1)
        ).scalar_one()
        generated = GeneratedDocument(
            encounter_id=encounter.id,
            client_id=client.id,
            template_id=template.id,
            document_number=issued.full_number,
            series=issued.series,
            blank_form_id=issued.id,
            blank_number_snapshot=issued.full_number,
            file_name="generated.docx",
            file_path="generated.docx",
        )
        client_document = ClientDocument(
            client_id=client.id,
            document_type="driver_certificate",
            blank_form_id=issued.id,
            blank_number_snapshot=issued.full_number,
        )
        db.add_all([generated, client_document])
        db.flush()
        issued.status = BLANK_STATUS_ISSUED
        issued.client_id = client.id
        issued.encounter_id = encounter.id
        issued.generated_document_id = generated.id
        issued.issued_at = datetime.utcnow()
        db.commit()
        return first, second, generated, client_document, issued.full_number

    def test_clear_removes_numbers_and_batches_of_one_center_only(self):
        with self.Session() as db:
            first, second, generated, client_document, issued_number = self._seed(db)

            result = clear_center_blanks(db, center_id=first.id, user_id=None)
            db.commit()

            self.assertEqual(result, {"batches_deleted": 2, "forms_deleted": 7, "documents_detached": 2})
            self.assertEqual(
                db.execute(select(BlankForm).where(BlankForm.center_id == first.id)).scalars().all(), []
            )
            self.assertEqual(list_batches(db, center_id=first.id), [])
            self.assertTrue(all(item["total"] == 0 for item in stats(db, center_id=first.id)))

            # Соседний медцентр не затронут.
            self.assertEqual(len(list_batches(db, center_id=second.id)), 1)
            self.assertEqual(
                len(db.execute(select(BlankForm).where(BlankForm.center_id == second.id)).scalars().all()), 5
            )

            # Документ остаётся, напечатанный номер сохраняется в снимке.
            db.refresh(generated)
            db.refresh(client_document)
            self.assertIsNone(generated.blank_form_id)
            self.assertEqual(generated.blank_number_snapshot, issued_number)
            self.assertIsNone(client_document.blank_form_id)
            self.assertEqual(client_document.blank_number_snapshot, issued_number)

            audit = db.execute(select(AuditLog).where(AuditLog.action == "clear_blanks")).scalar_one()
            self.assertEqual(audit.center_id, first.id)
            self.assertEqual(audit.payload_json["forms_by_status"], {BLANK_STATUS_FREE: 6, BLANK_STATUS_ISSUED: 1})

    def test_numbering_starts_over_after_clear(self):
        with self.Session() as db:
            first, *_ = self._seed(db)
            clear_center_blanks(db, center_id=first.id, user_id=None)
            db.commit()

            batch = create_batch(
                db,
                blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                series="40",
                number_from_input="1",
                number_to_input="5",
                received_at=None,
                comment=None,
                center_id=first.id,
                user_id=None,
            )
            auto_form = create_auto_number_form(
                db,
                blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                center_id=first.id,
                series="086У",
            )
            db.commit()

            self.assertEqual(batch.quantity, 5)
            self.assertEqual(auto_form.number_value, 1)
            self.assertEqual(len(list_batches(db, center_id=first.id)), 2)

    def test_only_chairman_or_admin_may_clear(self):
        for role_code in ("chairman", "admin"):
            user = SimpleNamespace(role=SimpleNamespace(code=role_code))
            self.assertIs(require_blank_clear_access(current_user=user), user)

        for role in (SimpleNamespace(code="registrar"), None):
            with self.assertRaises(HTTPException) as error:
                require_blank_clear_access(current_user=SimpleNamespace(role=role))
            self.assertEqual(error.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
