import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.blank_form import (  # noqa: E402
    BLANK_STATUS_FREE,
    BLANK_STATUS_ISSUED,
    BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE,
    BlankBatch,
    BlankForm,
)
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.document_template import DocumentTemplate  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.services.blank_forms import get_next_free_form, release_form  # noqa: E402
from app.services.document_generator import generate_document  # noqa: E402
from app.services.template_catalog import sync_document_template_catalog  # noqa: E402


class GimsChosenBlankTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.original_generated_dir = settings.generated_documents_dir
        self.temp_dir = tempfile.TemporaryDirectory()
        settings.generated_documents_dir = self.temp_dir.name

    def tearDown(self):
        settings.generated_documents_dir = self.original_generated_dir
        self.temp_dir.cleanup()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_print_uses_the_number_found_in_the_window_not_the_first_one_of_the_visit(self):
        """После первой печати «Найти номер» даёт следующий, и печатается именно он."""
        with self.Session() as db:
            sync_document_template_catalog(db)
            template = db.query(DocumentTemplate).filter(
                DocumentTemplate.blank_type == BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE,
                DocumentTemplate.template_type == "xls",
            ).one()
            center = Center(code="gims-chosen", name="Центр")
            client = Client(patient_number=1, last_name="Иванов", first_name="Иван", birth_date=date(1980, 2, 1))
            db.add_all([center, client])
            db.flush()
            encounter = Encounter(
                center_id=center.id,
                client_id=client.id,
                encounter_date=date(2026, 9, 29),
                payment_type="cash",
            )
            batch = BlankBatch(
                center_id=center.id,
                blank_type=BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE,
                series="ГИМС",
                number_from=1,
                number_to=3,
                number_width=7,
                quantity=3,
            )
            db.add_all([encounter, batch])
            db.flush()
            for value in range(1, 4):
                db.add(
                    BlankForm(
                        batch_id=batch.id,
                        center_id=center.id,
                        blank_type=BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE,
                        series="ГИМС",
                        number_value=value,
                        full_number=f"ГИМС{value:07d}",
                        status=BLANK_STATUS_FREE,
                    )
                )
            db.commit()

            def find_number():
                return get_next_free_form(
                    db,
                    blank_type=BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE,
                    center_id=center.id,
                    series="ГИМС",
                )

            def print_form(form):
                result = generate_document(
                    db,
                    template_id=template.id,
                    template_code=None,
                    client_id=client.id,
                    encounter_id=encounter.id,
                    blank_form_id=form.id,
                    print_variant="gims",
                )
                db.commit()
                return result

            first = find_number()
            self.assertEqual(print_form(first).blank_number, "ГИМС0000001")

            second = find_number()
            self.assertEqual(second.full_number, "ГИМС0000002")
            self.assertEqual(print_form(second).blank_number, "ГИМС0000002")
            self.assertEqual(db.get(BlankForm, second.id).status, BLANK_STATUS_ISSUED)

            # Повторная печать того же номера не тратит новый бланк.
            self.assertEqual(print_form(db.get(BlankForm, second.id)).blank_number, "ГИМС0000002")
            self.assertEqual(find_number().full_number, "ГИМС0000003")

            # Освобождённый номер возвращается в свободные и снова находится первым.
            release_form(db, form_id=first.id, user_id=1)
            db.commit()
            self.assertEqual(find_number().full_number, "ГИМС0000001")


if __name__ == "__main__":
    unittest.main()
