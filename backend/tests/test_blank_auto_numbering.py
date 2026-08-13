from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.models.blank_form import (  # noqa: E402
    BLANK_STATUS_FREE,
    BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
    BLANK_TYPE_LMK_MEDICAL_CERTIFICATE,
    BlankBatch,
    BlankForm,
    BlankType,
)
from app.services.blank_forms import create_auto_number_form, resolve_blank_type_for_series  # noqa: E402


class BlankAutoNumberingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    @staticmethod
    def _seed_blank_types(db):
        db.add_all(
            [
                BlankType(
                    code=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                    name="Водительская",
                    is_active=True,
                ),
                BlankType(
                    code=BLANK_TYPE_LMK_MEDICAL_CERTIFICATE,
                    name="ЛМК",
                    is_active=True,
                ),
            ]
        )
        db.flush()

    @staticmethod
    def _add_strict_blank(db, *, center_id: int, number_value: int):
        batch = BlankBatch(
            center_id=center_id,
            blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
            series="40",
            number_from=number_value,
            number_to=number_value,
            number_width=7,
            quantity=1,
            comment=None,
        )
        db.add(batch)
        db.flush()
        db.add(
            BlankForm(
                batch_id=batch.id,
                center_id=center_id,
                blank_type=batch.blank_type,
                series=batch.series,
                number_value=number_value,
                full_number=f"40{number_value:07d}",
                status=BLANK_STATUS_FREE,
            )
        )
        db.flush()

    def test_auto_numbers_are_shared_across_types_and_series(self):
        with self.Session() as db:
            self._seed_blank_types(db)

            first = create_auto_number_form(
                db,
                blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                center_id=1,
                series="086У",
            )
            second = create_auto_number_form(
                db,
                blank_type=BLANK_TYPE_LMK_MEDICAL_CERTIFICATE,
                center_id=1,
                series="ЛМК",
            )
            third = create_auto_number_form(
                db,
                blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                center_id=1,
                series="095У",
            )

            self.assertEqual(first.full_number, "086У0000001")
            self.assertEqual(second.full_number, "ЛМК0000002")
            self.assertEqual(third.full_number, "095У0000003")

    def test_strict_blanks_do_not_advance_auto_numbering(self):
        with self.Session() as db:
            self._seed_blank_types(db)
            self._add_strict_blank(db, center_id=1, number_value=999_999)

            automatic = create_auto_number_form(
                db,
                blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                center_id=1,
                series="СПОРТ",
            )

            self.assertEqual(automatic.number_value, 1)
            self.assertEqual(automatic.full_number, "СПОРТ0000001")

    def test_each_center_has_its_own_auto_sequence(self):
        with self.Session() as db:
            self._seed_blank_types(db)

            center_one = create_auto_number_form(
                db,
                blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                center_id=1,
                series="070У",
            )
            center_two = create_auto_number_form(
                db,
                blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                center_id=2,
                series="070У",
            )

            self.assertEqual(center_one.number_value, 1)
            self.assertEqual(center_two.number_value, 1)

    def test_legacy_driver_lookup_uses_specialized_lmk_type(self):
        self.assertEqual(
            resolve_blank_type_for_series(BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE, "ЛМК"),
            BLANK_TYPE_LMK_MEDICAL_CERTIFICATE,
        )
        self.assertEqual(
            resolve_blank_type_for_series(BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE, "ЛМК-Н"),
            BLANK_TYPE_LMK_MEDICAL_CERTIFICATE,
        )


if __name__ == "__main__":
    unittest.main()
