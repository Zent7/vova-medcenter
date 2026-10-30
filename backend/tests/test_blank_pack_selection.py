from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.blanks import manual_pick_endpoint  # noqa: E402
from app.api.v1.routes.documents import generate_document_file  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.blank_form import (  # noqa: E402
    BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
    BLANK_TYPE_LMK_MEDICAL_CERTIFICATE,
    BlankForm,
    BlankType,
)
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.document_template import DocumentTemplate  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.models.generated_document import GeneratedDocument  # noqa: E402
from app.models.user import Role, User  # noqa: E402
from app.schemas.document_generation import DocumentGenerateRequest  # noqa: E402
from app.services.blank_forms import (  # noqa: E402
    BlankServiceError,
    create_auto_number_form,
    create_batch,
    get_form_by_printed_number,
    get_next_free_form,
    issue_specific_blank,
    list_free_series,
    release_form,
    split_batch_into_parts,
)


DRIVER = BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE


class BlankPackSelectionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.temp = tempfile.TemporaryDirectory()
        self.original_generated_dir = settings.generated_documents_dir
        settings.generated_documents_dir = self.temp.name
        self.center = Center(code="pack-center", name="Медцентр")
        self.other_center = Center(code="other-center", name="Другой медцентр")
        role = Role(code="chairman", name="Председатель")
        self.client = Client(patient_number=1, last_name="Иванов", first_name="Иван", birth_date=date(1980, 1, 1))
        self.other_client = Client(patient_number=2, last_name="Петров", first_name="Пётр", birth_date=date(1985, 1, 1))
        self.db.add_all([self.center, self.other_center, role, self.client, self.other_client])
        self.db.flush()
        self.actor = User(
            id=2, role_id=role.id, center_id=self.center.id, login="pack-operator",
            password_hash="test", full_name="Оператор пачки",
        )
        self.encounter = Encounter(
            center_id=self.center.id, client_id=self.client.id,
            encounter_date=date(2026, 10, 30), payment_type="cash",
        )
        self.other_encounter = Encounter(
            center_id=self.center.id, client_id=self.other_client.id,
            encounter_date=date(2026, 10, 30), payment_type="cash",
        )
        self.db.add_all([self.actor, self.encounter, self.other_encounter, BlankType(code=DRIVER, name="Водительская")])
        self.db.flush()
        self.batch = create_batch(
            self.db, blank_type=DRIVER, series="41", number_from_input=1, number_to_input=10,
            received_at=None, comment=None, center_id=self.center.id, user_id=self.actor.id,
        )
        self.first, self.second = split_batch_into_parts(
            self.db, batch_id=self.batch.id, pack_size=5, user_id=self.actor.id,
        )
        template_path = Path(self.temp.name) / "pack-selection.xml"
        template_path.write_text("<certificate>[BlankNumber]</certificate>", encoding="utf-8")
        self.template = DocumentTemplate(
            code="pack_selection_test", name="Проверка пачек", file_name=template_path.name,
            file_path=str(template_path), template_type="xml", output_format="xml",
            requires_numbered_blank=True, blank_type=DRIVER,
        )
        self.db.add(self.template)
        self.db.commit()

    def tearDown(self):
        settings.generated_documents_dir = self.original_generated_dir
        self.db.close()
        self.engine.dispose()
        self.temp.cleanup()

    def _form(self, number):
        return self.db.execute(select(BlankForm).where(BlankForm.batch_id == self.batch.id, BlankForm.number_value == number)).scalar_one()

    def _issue(self, number, client=None, encounter=None, **extra):
        return issue_specific_blank(
            self.db, form_id=self._form(number).id, blank_type=DRIVER,
            center_id=self.center.id, client_id=(client or self.client).id,
            encounter_id=(encounter or self.encounter).id, user_id=self.actor.id, **extra,
        )

    def _print(self, form):
        return generate_document_file(
            DocumentGenerateRequest(template_id=self.template.id, client_id=self.client.id,
                                    encounter_id=self.encounter.id, blank_form_id=form.id),
            db=self.db, current_user=self.actor,
        )

    def test_a_later_pack_does_not_skip_numbers_in_another_operators_pack(self):
        self._issue(8)
        self.db.commit()
        first_next = get_next_free_form(self.db, blank_type=DRIVER, center_id=self.center.id, batch_part_id=self.first.id)
        second_next = get_next_free_form(self.db, blank_type=DRIVER, center_id=self.center.id, batch_part_id=self.second.id)
        self.assertEqual(first_next.number_value, 1)
        self.assertEqual(second_next.number_value, 9)
        self.assertEqual(list_free_series(self.db, blank_type=DRIVER, center_id=self.center.id)[0]["free_count"], 7)

    def test_releasing_a_number_advances_only_its_own_pack(self):
        released = self._issue(8)
        release_form(self.db, form_id=released.id, user_id=self.actor.id)
        self.db.commit()
        self.assertEqual(get_next_free_form(self.db, blank_type=DRIVER, batch_part_id=self.first.id).number_value, 1)
        self.assertEqual(get_next_free_form(self.db, blank_type=DRIVER, batch_part_id=self.second.id).number_value, 9)

    def test_manual_number_must_belong_to_the_chosen_pack_and_center(self):
        kwargs = dict(blank_type=DRIVER, center_id=self.center.id, series="41", number_input="000008")
        self.assertIsNone(get_form_by_printed_number(self.db, **kwargs, batch_part_id=self.first.id))
        found = get_form_by_printed_number(self.db, **kwargs, batch_part_id=self.second.id)
        self.assertEqual(found.id, self._form(8).id)
        kwargs["center_id"] = self.other_center.id
        self.assertIsNone(get_form_by_printed_number(self.db, **kwargs, batch_part_id=self.second.id))

    def test_manual_pick_and_print_record_the_actual_operator_and_pack(self):
        form = self._form(8)
        response = manual_pick_endpoint(form.id, db=self.db, current_user=self.actor)
        self.assertEqual(response.batch_part_id, self.second.id)
        result = self._print(form)
        self.assertEqual(result.blank_number, form.full_number)
        self.assertEqual(self.db.get(GeneratedDocument, result.generated_document_id).generated_by_user_id, self.actor.id)
        self.assertEqual(form.issued_by_user_id, self.actor.id)
        logs = self.db.execute(select(AuditLog).where(AuditLog.entity_type == "blank_form", AuditLog.entity_id == form.id)).scalars().all()
        self.assertEqual({entry.action for entry in logs}, {"manual_pick", "issue"})
        self.assertTrue(all(entry.user_id == self.actor.id for entry in logs))
        self.assertTrue(all(entry.payload_json["batch_part_id"] == self.second.id for entry in logs))

    def test_an_explicit_occupied_number_cannot_fall_back_to_an_earlier_print(self):
        first = self._print(self._form(1))
        occupied = self._issue(8, client=self.other_client, encounter=self.other_encounter)
        self.db.commit()
        with self.assertRaises(HTTPException) as raised:
            self._print(occupied)
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("занят", raised.exception.detail)
        self.assertEqual(self.db.query(GeneratedDocument).count(), 1)
        self.assertTrue(Path(first.output_file_path).is_file())

    def test_reprinting_the_same_number_for_the_same_encounter_is_idempotent(self):
        first = self._print(self._form(8))
        second = self._print(self._form(8))
        self.assertEqual(first.blank_number, second.blank_number)
        self.assertEqual(self.db.query(BlankForm).filter(BlankForm.status == "issued").count(), 1)

    def test_reuse_still_checks_the_center_and_type(self):
        self._issue(8)
        self.db.commit()
        with self.assertRaises(BlankServiceError):
            issue_specific_blank(
                self.db, form_id=self._form(8).id, blank_type=DRIVER,
                client_id=self.client.id, encounter_id=self.encounter.id,
                center_id=self.other_center.id, allow_reuse=True,
            )

    def test_manual_pick_rejects_another_centers_operator(self):
        self.actor.center_id = self.other_center.id
        self.db.commit()
        with self.assertRaises(HTTPException) as raised:
            manual_pick_endpoint(self._form(8).id, db=self.db, current_user=self.actor)
        self.assertEqual(raised.exception.status_code, 403)

    def test_manual_lmk_number_can_be_found_in_a_pack_without_a_printed_series(self):
        lmk_type = BLANK_TYPE_LMK_MEDICAL_CERTIFICATE
        self.db.add(BlankType(code=lmk_type, name="ЛМК"))
        self.db.flush()
        batch = create_batch(
            self.db, blank_type=lmk_type, series=None, number_from_input=1, number_to_input=10,
            received_at=None, comment=None, center_id=self.center.id, user_id=self.actor.id,
        )
        first, second = split_batch_into_parts(self.db, batch_id=batch.id, pack_size=5, user_id=self.actor.id)
        self.db.commit()
        kwargs = dict(blank_type=lmk_type, center_id=self.center.id, series="ЛМК", number_input="000008")
        self.assertIsNone(get_form_by_printed_number(self.db, **kwargs, batch_part_id=first.id))
        form = get_form_by_printed_number(self.db, **kwargs, batch_part_id=second.id)
        self.assertEqual(form.full_number, "000008")

    def test_manual_pick_accepts_stock_numbers_and_rejects_auto_created_numbers(self):
        form = create_auto_number_form(
            self.db, blank_type=DRIVER, center_id=self.center.id, series="ГТО", user_id=self.actor.id,
        )
        self.db.commit()
        with self.assertRaises(HTTPException) as raised:
            manual_pick_endpoint(form.id, db=self.db, current_user=self.actor)
        self.assertEqual(raised.exception.status_code, 404)
        self.assertIn("заведённой партии", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
