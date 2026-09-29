import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.models.blank_form import (  # noqa: E402
    BLANK_STATUS_FREE,
    BLANK_STATUS_ISSUED,
    BLANK_STATUS_SPOILED,
    BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE,
    BlankBatch,
    BlankForm,
)
from app.services.blank_forms import get_next_free_form, list_free_series, release_form  # noqa: E402


GIMS = BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE


class SkipUsedNumbersTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _add_batch(self, db, series, numbers, statuses=None, center_id=1):
        batch = BlankBatch(
            center_id=center_id,
            blank_type=GIMS,
            series=series,
            number_from=min(numbers),
            number_to=max(numbers),
            number_width=6,
            quantity=len(numbers),
        )
        db.add(batch)
        db.flush()
        forms = []
        for value in numbers:
            status = (statuses or {}).get(value, BLANK_STATUS_FREE)
            form = BlankForm(
                batch_id=batch.id,
                center_id=center_id,
                blank_type=GIMS,
                series=series,
                number_value=value,
                full_number=f"{series}{value:06d}",
                status=status,
                client_id=1 if status == BLANK_STATUS_ISSUED else None,
                encounter_id=1 if status == BLANK_STATUS_ISSUED else None,
                issued_at=datetime(2026, 9, 29, tzinfo=timezone.utc) if status == BLANK_STATUS_ISSUED else None,
            )
            db.add(form)
            forms.append(form)
        db.flush()
        return forms

    def test_series_with_only_skipped_numbers_is_not_offered_and_the_new_series_is(self):
        """Серия 40 закончилась, партия ГМ заведена позже: окно должно перейти на ГМ."""
        with self.Session() as db:
            old = self._add_batch(
                db,
                "40",
                [1, 2, 3],
                {1: BLANK_STATUS_ISSUED, 2: BLANK_STATUS_ISSUED, 3: BLANK_STATUS_ISSUED},
            )
            # Последний номер освободили: он свободен, но использован ниже по порядку.
            old[2].status = BLANK_STATUS_ISSUED
            db.flush()
            release_form(db, form_id=old[2].id, user_id=1)
            self._add_batch(db, "ГМ", [1, 2, 3])
            db.commit()

            series = list_free_series(db, blank_type=GIMS, center_id=1)
            self.assertEqual([item["series"] for item in series], ["ГМ"])
            self.assertEqual(series[0]["free_count"], 3)
            self.assertEqual(series[0]["next_full_number"], "ГМ000001")

            self.assertIsNone(get_next_free_form(db, blank_type=GIMS, center_id=1, series="40"))
            found = get_next_free_form(db, blank_type=GIMS, center_id=1, series="ГМ")
            self.assertEqual(found.full_number, "ГМ000001")
            # Без серии номер тоже берётся из ГМ: числа старой серии не должны
            # «перекрывать» малые номера новой партии.
            found = get_next_free_form(db, blank_type=GIMS, center_id=1)
            self.assertEqual(found.full_number, "ГМ000001")

    def test_spoiled_number_counts_as_used(self):
        with self.Session() as db:
            self._add_batch(db, "ГМ", [1, 2, 3], {1: BLANK_STATUS_SPOILED})
            db.commit()
            found = get_next_free_form(db, blank_type=GIMS, center_id=1, series="ГМ")
            self.assertEqual(found.full_number, "ГМ000002")

    def test_a_later_batch_with_lower_numbers_is_not_skipped(self):
        with self.Session() as db:
            self._add_batch(db, "40", [100, 101], {100: BLANK_STATUS_ISSUED, 101: BLANK_STATUS_ISSUED})
            self._add_batch(db, "40", [10, 11])
            db.commit()
            found = get_next_free_form(db, blank_type=GIMS, center_id=1, series="40")
            self.assertEqual(found.number_value, 10)
            series = list_free_series(db, blank_type=GIMS, center_id=1)
            self.assertEqual([(item["series"], item["free_count"]) for item in series], [("40", 2)])

    def test_released_number_is_not_offered_again_but_stays_free(self):
        with self.Session() as db:
            forms = self._add_batch(db, "ГМ", [1, 2, 3], {1: BLANK_STATUS_ISSUED, 2: BLANK_STATUS_ISSUED})
            release_form(db, form_id=forms[1].id, user_id=1)
            db.commit()
            self.assertEqual(db.get(BlankForm, forms[1].id).status, BLANK_STATUS_FREE)
            found = get_next_free_form(db, blank_type=GIMS, center_id=1, series="ГМ")
            self.assertEqual(found.full_number, "ГМ000003")


if __name__ == "__main__":
    unittest.main()
