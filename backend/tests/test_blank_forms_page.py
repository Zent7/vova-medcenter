from datetime import date, datetime
from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.blanks import get_forms_page  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.blank_form import (  # noqa: E402
    BLANK_STATUS_FREE,
    BLANK_STATUS_ISSUED,
    NUMBERED_BLANK_TYPES,
    BlankBatch,
    BlankForm,
)
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.services.blank_forms import list_forms  # noqa: E402


class BlankFormsPageTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _seed_forms(self, db):
        center = Center(code="center-1", name="Медцентр 1")
        other_center = Center(code="center-2", name="Медцентр 2")
        client = Client(
            patient_number=1,
            last_name="Иванов",
            first_name="Иван",
            birth_date=date(1980, 1, 1),
        )
        db.add_all([center, other_center, client])
        db.flush()

        for type_index, (blank_type, _name) in enumerate(NUMBERED_BLANK_TYPES):
            first_batch = BlankBatch(
                center_id=center.id,
                blank_type=blank_type,
                series=f"T{type_index}A",
                number_from=1,
                number_to=6,
                number_width=6,
                quantity=6,
            )
            second_batch = BlankBatch(
                center_id=center.id,
                blank_type=blank_type,
                series=f"T{type_index}B",
                number_from=7,
                number_to=11,
                number_width=6,
                quantity=5,
            )
            db.add_all([first_batch, second_batch])
            db.flush()

            for value in range(1, 12):
                batch = first_batch if value <= 6 else second_batch
                db.add(
                    BlankForm(
                        batch_id=batch.id,
                        center_id=center.id,
                        blank_type=blank_type,
                        series=batch.series,
                        number_value=value,
                        full_number=f"{batch.series}{value:06d}",
                        status=BLANK_STATUS_ISSUED if blank_type == NUMBERED_BLANK_TYPES[0][0] and value == 2 else BLANK_STATUS_FREE,
                        client_id=client.id if blank_type == NUMBERED_BLANK_TYPES[0][0] and value == 2 else None,
                        issued_at=datetime.utcnow() if blank_type == NUMBERED_BLANK_TYPES[0][0] and value == 2 else None,
                    )
                )

        other_batch = BlankBatch(
            center_id=other_center.id,
            blank_type=NUMBERED_BLANK_TYPES[0][0],
            series="OTHER",
            number_from=1,
            number_to=1,
            number_width=6,
            quantity=1,
        )
        db.add(other_batch)
        db.flush()
        db.add(
            BlankForm(
                batch_id=other_batch.id,
                center_id=other_center.id,
                blank_type=other_batch.blank_type,
                series=other_batch.series,
                number_value=1,
                full_number="OTHER000001",
                status=BLANK_STATUS_FREE,
            )
        )
        db.commit()
        return center.id

    def test_forms_page_returns_all_types_across_batches_in_pages(self):
        with self.Session() as db:
            center_id = self._seed_forms(db)

            page = get_forms_page(
                blank_type=None,
                blank_status=None,
                center_id=center_id,
                search=None,
                limit=50,
                offset=0,
                db=db,
            )
            self.assertEqual(page.total, 55)
            self.assertEqual(page.limit, 50)
            self.assertEqual(page.offset, 0)
            self.assertEqual(len(page.items), 50)
            self.assertEqual(
                {item.blank_type for item in page.items},
                {code for code, _name in NUMBERED_BLANK_TYPES},
            )
            self.assertEqual(
                [item.blank_type for item in page.items[:11]],
                [NUMBERED_BLANK_TYPES[0][0]] * 11,
            )

            second_page = get_forms_page(
                blank_type=None,
                blank_status=None,
                center_id=center_id,
                search=None,
                limit=50,
                offset=50,
                db=db,
            )
            self.assertEqual(second_page.total, 55)
            self.assertEqual(len(second_page.items), 5)

    def test_forms_page_filters_by_status_type_search_and_center(self):
        with self.Session() as db:
            center_id = self._seed_forms(db)
            driver_type = NUMBERED_BLANK_TYPES[0][0]

            issued_page = get_forms_page(
                blank_type=None,
                blank_status=BLANK_STATUS_ISSUED,
                center_id=center_id,
                search=None,
                limit=50,
                offset=0,
                db=db,
            )
            self.assertEqual(issued_page.total, 1)
            self.assertEqual(issued_page.items[0].client_full_name, "Иванов Иван")

            typed_page = get_forms_page(
                blank_type=NUMBERED_BLANK_TYPES[2][0],
                blank_status=None,
                center_id=center_id,
                search=None,
                limit=50,
                offset=0,
                db=db,
            )
            self.assertEqual(typed_page.total, 11)
            self.assertTrue(all(item.blank_type == NUMBERED_BLANK_TYPES[2][0] for item in typed_page.items))

            search_page = get_forms_page(
                blank_type=None,
                blank_status=None,
                center_id=center_id,
                search="Иванов",
                limit=50,
                offset=0,
                db=db,
            )
            self.assertEqual(search_page.total, 1)
            self.assertEqual(search_page.items[0].blank_type, driver_type)

            all_centers_page = get_forms_page(
                blank_type=None,
                blank_status=None,
                center_id=None,
                search=None,
                limit=100,
                offset=0,
                db=db,
            )
            self.assertEqual(all_centers_page.total, 56)

    def test_legacy_forms_list_remains_batch_compatible(self):
        with self.Session() as db:
            center_id = self._seed_forms(db)
            batch = db.query(BlankBatch).filter(BlankBatch.center_id == center_id).first()

            items = list_forms(db, center_id=center_id, batch_id=batch.id, limit=1000)
            page = get_forms_page(
                blank_type=None,
                batch_id=batch.id,
                blank_status=None,
                center_id=center_id,
                search=None,
                limit=50,
                offset=0,
                db=db,
            )

            self.assertEqual(len(items), batch.quantity)
            self.assertTrue(all(item.batch_id == batch.id for item in items))
            self.assertEqual(page.total, batch.quantity)
            self.assertTrue(all(item.batch_id == batch.id for item in page.items))


if __name__ == "__main__":
    unittest.main()
