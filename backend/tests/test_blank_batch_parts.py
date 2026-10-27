from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.blank_form import (  # noqa: E402
    BLANK_STATUS_FREE,
    BLANK_STATUS_ISSUED,
    BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
    BlankForm,
    BlankType,
)
from app.services.blank_forms import (  # noqa: E402
    BlankNotFreeError,
    BlankPartsExistError,
    BlankRangeInvalidError,
    create_batch,
    get_next_free_form,
    list_batch_parts_with_counts,
    manual_pick_form,
    split_batch_into_parts,
)


class BlankBatchPartsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.db.add(BlankType(code=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE, name="Водительская", is_active=True))
        self.db.flush()
        self.batch = create_batch(
            self.db,
            blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
            series="41",
            number_from_input="1",
            number_to_input="1000",
            received_at=None,
            comment=None,
            center_id=None,
            user_id=1,
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _forms_with_numbers(self, numbers):
        return list(
            self.db.execute(
                select(BlankForm).where(BlankForm.batch_id == self.batch.id, BlankForm.number_value.in_(numbers))
            ).scalars()
        )

    def test_split_gives_consecutive_packs_and_assigns_every_blank(self):
        parts = split_batch_into_parts(self.db, batch_id=self.batch.id, pack_size=500, user_id=1)
        self.db.commit()

        self.assertEqual([(part.number_from, part.number_to) for part in parts], [(1, 500), (501, 1000)])
        counts = list_batch_parts_with_counts(self.db, [self.batch.id])[self.batch.id]
        self.assertEqual([(item["free_count"], item["issued_count"]) for item in counts], [(500, 0), (500, 0)])
        unassigned = self.db.execute(
            select(BlankForm.id).where(BlankForm.batch_id == self.batch.id, BlankForm.batch_part_id.is_(None))
        ).all()
        self.assertEqual(unassigned, [])

    def test_last_pack_takes_the_remainder(self):
        parts = split_batch_into_parts(self.db, batch_id=self.batch.id, pack_size=300, user_id=1)
        self.db.commit()

        self.assertEqual(
            [(part.number_from, part.number_to) for part in parts],
            [(1, 300), (301, 600), (601, 900), (901, 1000)],
        )

    def test_batch_can_be_split_only_once(self):
        split_batch_into_parts(self.db, batch_id=self.batch.id, pack_size=500, user_id=1)
        self.db.commit()

        with self.assertRaises(BlankPartsExistError):
            split_batch_into_parts(self.db, batch_id=self.batch.id, pack_size=250, user_id=1)

    def test_pack_size_must_be_positive(self):
        with self.assertRaises(BlankRangeInvalidError):
            split_batch_into_parts(self.db, batch_id=self.batch.id, pack_size=0, user_id=1)

    def test_next_blank_comes_only_from_the_chosen_pack(self):
        first, second = split_batch_into_parts(self.db, batch_id=self.batch.id, pack_size=500, user_id=1)
        self.db.commit()

        form = get_next_free_form(self.db, blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE, batch_part_id=second.id)
        self.assertEqual(form.number_value, 501)

    def test_exhausted_pack_gives_no_blank_and_others_stay_available(self):
        first, _second = split_batch_into_parts(self.db, batch_id=self.batch.id, pack_size=500, user_id=1)
        self.db.commit()
        for form in self._forms_with_numbers(range(1, 501)):
            form.status = BLANK_STATUS_ISSUED
        self.db.commit()

        self.assertIsNone(
            get_next_free_form(self.db, blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE, batch_part_id=first.id)
        )
        counts = list_batch_parts_with_counts(self.db, [self.batch.id])[self.batch.id]
        self.assertEqual((counts[0]["free_count"], counts[0]["issued_count"]), (0, 500))
        self.assertEqual((counts[1]["free_count"], counts[1]["issued_count"]), (500, 0))

    def test_manual_pick_of_a_free_blank_is_written_to_history(self):
        form = self._forms_with_numbers([42])[0]
        picked = manual_pick_form(self.db, form_id=form.id, user_id=1)
        self.db.commit()

        self.assertEqual(picked.full_number, form.full_number)
        entries = self.db.execute(
            select(AuditLog).where(AuditLog.entity_type == "blank_form", AuditLog.action == "manual_pick")
        ).scalars().all()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].entity_id, form.id)

    def test_manual_pick_refuses_a_blank_that_is_not_free(self):
        form = self._forms_with_numbers([7])[0]
        form.status = BLANK_STATUS_ISSUED
        self.db.commit()

        with self.assertRaises(BlankNotFreeError):
            manual_pick_form(self.db, form_id=form.id, user_id=1)


if __name__ == "__main__":
    unittest.main()
