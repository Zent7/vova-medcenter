"""Типографские бланки ЛМК заводятся без серии — на бумаге только номер.

Окно печати называет такой бланк серией «ЛМК», хотя это название типа.
Раньше поиск фильтровал выдачу по `series = 'ЛМК'` и не находил ни одного
заведённого номера.
"""

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
    BLANK_STATUS_ISSUED,
    BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
    BLANK_TYPE_LMK_MEDICAL_CERTIFICATE,
    BlankBatch,
    BlankForm,
)
from app.models.center import Center  # noqa: E402
from app.services.blank_forms import get_next_free_form, normalize_lookup_series  # noqa: E402


class LmkBlankLookupTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _add_form(
        self,
        db,
        *,
        number,
        series=None,
        center_id=1,
        blank_type=BLANK_TYPE_LMK_MEDICAL_CERTIFICATE,
        status=BLANK_STATUS_FREE,
    ):
        batch = BlankBatch(
            center_id=center_id,
            blank_type=blank_type,
            series=series,
            number_from=number,
            number_to=number,
            number_width=6,
            quantity=1,
        )
        db.add(batch)
        db.flush()
        form = BlankForm(
            batch_id=batch.id,
            blank_type=blank_type,
            center_id=center_id,
            series=series,
            number_value=number,
            full_number=f"{series or ''}{number:06d}",
            status=status,
        )
        db.add(form)
        db.flush()
        return form

    def _seed_centers(self, db):
        db.add(Center(id=1, code="center-1", name="Медцентр 1"))
        db.add(Center(id=2, code="center-2", name="Медцентр 2"))
        db.flush()

    def _find_lmk(self, db, center_id=1):
        """Так «Найти номер» запрашивает бланк ЛМК из окна печати."""

        return get_next_free_form(
            db,
            blank_type=BLANK_TYPE_LMK_MEDICAL_CERTIFICATE,
            center_id=center_id,
            series="ЛМК",
        )

    def test_series_named_after_the_type_is_not_used_as_a_filter(self):
        self.assertIsNone(normalize_lookup_series(BLANK_TYPE_LMK_MEDICAL_CERTIFICATE, "ЛМК"))
        self.assertIsNone(normalize_lookup_series(BLANK_TYPE_LMK_MEDICAL_CERTIFICATE, "лмк"))
        self.assertIsNone(normalize_lookup_series(BLANK_TYPE_LMK_MEDICAL_CERTIFICATE, "LMK"))

    def test_real_series_is_left_alone(self):
        self.assertEqual(
            normalize_lookup_series(BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE, "ЛМК"),
            "ЛМК",
        )
        self.assertEqual(
            normalize_lookup_series(BLANK_TYPE_LMK_MEDICAL_CERTIFICATE, "40"),
            "40",
        )

    def test_print_dialog_finds_a_blank_entered_without_a_series(self):
        with self.Session() as db:
            self._seed_centers(db)
            self._add_form(db, number=123)

            found = self._find_lmk(db)
            self.assertIsNotNone(found, "бланк без серии должен находиться")
            self.assertEqual(found.number_value, 123)

    def test_lookup_stays_inside_its_center_and_skips_issued_blanks(self):
        with self.Session() as db:
            self._seed_centers(db)
            self._add_form(db, number=10, status=BLANK_STATUS_ISSUED)
            self._add_form(db, number=11, center_id=2)
            self._add_form(db, number=12)

            self.assertEqual(self._find_lmk(db).number_value, 12)
            self.assertEqual(self._find_lmk(db, center_id=2).number_value, 11)

    def test_lmk_range_entered_with_a_series_is_found_too(self):
        """Если серию всё же вписали при заведении партии, номер тоже находится."""

        with self.Session() as db:
            self._seed_centers(db)
            self._add_form(db, number=77, series="77")

            self.assertEqual(self._find_lmk(db).number_value, 77)

    def test_without_a_loaded_range_nothing_is_found(self):
        with self.Session() as db:
            self._seed_centers(db)
            self.assertIsNone(self._find_lmk(db))

    def test_driver_blanks_are_still_matched_by_their_printed_series(self):
        with self.Session() as db:
            self._seed_centers(db)
            self._add_form(
                db,
                number=500,
                series="40",
                blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
            )

            self.assertIsNone(
                get_next_free_form(
                    db,
                    blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                    center_id=1,
                    series="4024",
                )
            )
            found = get_next_free_form(
                db,
                blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                center_id=1,
                series="40",
            )
            self.assertEqual(found.number_value, 500)


if __name__ == "__main__":
    unittest.main()
