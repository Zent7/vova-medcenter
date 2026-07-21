from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
import app.db.init_db as init_db_module  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.blank_form import (  # noqa: E402
    BLANK_STATUS_FREE,
    BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
    BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE,
    BLANK_TYPE_GUARD_MEDICAL_CERTIFICATE,
    BLANK_TYPE_LMK_MEDICAL_CERTIFICATE,
    BLANK_TYPE_TRACTOR_MEDICAL_CERTIFICATE,
    NUMBERED_BLANK_TYPES,
    BlankBatch,
    BlankForm,
    BlankType,
)
from app.models.document_template import DocumentTemplate  # noqa: E402
from app.services.blank_forms import list_blank_types  # noqa: E402
from app.services.template_catalog import sync_document_template_catalog  # noqa: E402


class BlankTypeTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_numbered_blank_types_match_operator_categories(self):
        self.assertEqual(
            NUMBERED_BLANK_TYPES,
            (
                (BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE, "Водительская"),
                (BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE, "ГИМС"),
                (BLANK_TYPE_TRACTOR_MEDICAL_CERTIFICATE, "Тракторная"),
                (BLANK_TYPE_GUARD_MEDICAL_CERTIFICATE, "Охранная"),
                (BLANK_TYPE_LMK_MEDICAL_CERTIFICATE, "ЛМК"),
            ),
        )

    def test_blank_type_list_uses_operator_order(self):
        with self.Session() as db:
            for code, name in reversed(NUMBERED_BLANK_TYPES):
                db.add(BlankType(code=code, name=name, is_active=True))
            db.commit()

            self.assertEqual(
                [item.code for item in list_blank_types(db)],
                [code for code, _name in NUMBERED_BLANK_TYPES],
            )

    def test_seed_reclassifies_existing_lmk_and_gims_rows(self):
        with self.Session() as db:
            lmk_batch = BlankBatch(
                center_id=None,
                blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                series="ЛМК",
                number_from=1,
                number_to=1,
                number_width=7,
                quantity=1,
            )
            gims_batch = BlankBatch(
                center_id=None,
                blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                series="ГИМС",
                number_from=1,
                number_to=1,
                number_width=7,
                quantity=1,
            )
            db.add_all([lmk_batch, gims_batch])
            db.flush()
            db.add_all(
                [
                    BlankForm(
                        batch_id=lmk_batch.id,
                        center_id=None,
                        blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                        series="ЛМК",
                        number_value=1,
                        full_number="ЛМК0000001",
                        status=BLANK_STATUS_FREE,
                    ),
                    BlankForm(
                        batch_id=gims_batch.id,
                        center_id=None,
                        blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                        series="ГИМС",
                        number_value=1,
                        full_number="ГИМС0000001",
                        status=BLANK_STATUS_FREE,
                    ),
                ]
            )
            db.commit()

        original_engine = init_db_module.engine
        original_session_local = init_db_module.SessionLocal
        init_db_module.engine = self.engine
        init_db_module.SessionLocal = self.Session
        try:
            init_db_module.seed_blank_types()
        finally:
            init_db_module.engine = original_engine
            init_db_module.SessionLocal = original_session_local

        with self.Session() as db:
            batches = {item.series: item.blank_type for item in db.query(BlankBatch).all()}
            forms = {item.series: item.blank_type for item in db.query(BlankForm).all()}
            self.assertEqual(batches["ЛМК"], BLANK_TYPE_LMK_MEDICAL_CERTIFICATE)
            self.assertEqual(batches["ГИМС"], BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE)
            self.assertEqual(forms["ЛМК"], BLANK_TYPE_LMK_MEDICAL_CERTIFICATE)
            self.assertEqual(forms["ГИМС"], BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE)

    def test_template_catalog_assigns_specialized_blank_types(self):
        with self.Session() as db:
            sync_document_template_catalog(db)
            db.commit()

            gims_template = db.query(DocumentTemplate).filter(
                DocumentTemplate.file_name == "ГИМС_шаблон_для_загрузки_из_файла.xml"
            ).one()
            lmk_templates = db.query(DocumentTemplate).filter(
                DocumentTemplate.file_name.ilike("%ЛМК%")
            ).all()

            self.assertEqual(gims_template.blank_type, BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE)
            self.assertTrue(gims_template.requires_numbered_blank)
            self.assertTrue(lmk_templates)
            self.assertTrue(all(item.blank_type == BLANK_TYPE_LMK_MEDICAL_CERTIFICATE for item in lmk_templates))
            self.assertTrue(all(item.requires_numbered_blank for item in lmk_templates))


if __name__ == "__main__":
    unittest.main()
