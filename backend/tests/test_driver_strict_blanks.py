from datetime import date
from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.models.blank_form import (  # noqa: E402
    BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
    BlankBatch,
    BlankForm,
    BlankType,
)
from app.models.client import Client  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.services.blank_forms import (  # noqa: E402
    NoFreeBlankError,
    create_auto_number_form,
    get_next_free_form,
    issue_next_blank,
    list_free_series,
)


DRIVER = BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE


class DriverStrictBlanksTests(unittest.TestCase):
    """ВУ берёт номер только из заведённой партии, а не из остатков автонумерации."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    @staticmethod
    def _seed(db):
        db.add(BlankType(code=DRIVER, name="Водительская", is_active=True))
        db.flush()

    @staticmethod
    def _add_stock_batch(db, series="40", numbers=(1, 2, 3), center_id=1):
        batch = BlankBatch(
            center_id=center_id,
            blank_type=DRIVER,
            series=series,
            number_from=min(numbers),
            number_to=max(numbers),
            number_width=7,
            quantity=len(numbers),
        )
        db.add(batch)
        db.flush()
        for value in numbers:
            db.add(
                BlankForm(
                    batch_id=batch.id,
                    center_id=center_id,
                    blank_type=DRIVER,
                    series=series,
                    number_value=value,
                    full_number=f"{series}{value:07d}",
                    status="free",
                )
            )
        db.flush()

    def test_leftover_auto_number_is_not_offered_to_a_strict_driver_blank(self):
        with self.Session() as db:
            self._seed(db)
            self._add_stock_batch(db, "40", (1, 2))
            # Окно печати создало автономер серии 41, печать не состоялась: он остался свободным.
            create_auto_number_form(db, blank_type=DRIVER, center_id=1, series="41")

            self.assertIsNone(
                get_next_free_form(db, blank_type=DRIVER, center_id=1, series="41", strict_only=True)
            )
            self.assertEqual(
                [item["series"] for item in list_free_series(db, blank_type=DRIVER, center_id=1, strict_only=True)],
                ["40"],
            )

    def test_certificate_lookup_still_sees_leftover_auto_number(self):
        """Справки на обычной бумаге (ГТО, 095у) по-прежнему берут свободный автономер."""

        with self.Session() as db:
            self._seed(db)
            leftover = create_auto_number_form(db, blank_type=DRIVER, center_id=1, series="095У")

            found = get_next_free_form(db, blank_type=DRIVER, center_id=1, series="095У")

            self.assertIsNotNone(found)
            self.assertEqual(found.id, leftover.id)
            self.assertEqual(
                [item["series"] for item in list_free_series(db, blank_type=DRIVER, center_id=1)],
                ["095У"],
            )

    def test_strict_lookup_finds_a_stock_batch_of_any_series(self):
        """Партия ВУ с любой серией находится, даже если такой серии нет в списке справок."""

        with self.Session() as db:
            self._seed(db)
            self._add_stock_batch(db, "41", (100, 101))

            found = get_next_free_form(db, blank_type=DRIVER, center_id=1, series="41", strict_only=True)

            self.assertIsNotNone(found)
            self.assertEqual(found.full_number, "410000100")

    def test_implicit_issue_skips_auto_numbers(self):
        with self.Session() as db:
            self._seed(db)
            create_auto_number_form(db, blank_type=DRIVER, center_id=1, series="ГТО")
            client = Client(patient_number=1, last_name="Тест", first_name="Тест", birth_date=date(1980, 1, 1))
            db.add(client)
            db.flush()
            encounter = Encounter(
                center_id=1,
                client_id=client.id,
                encounter_date=date(2026, 9, 30),
                payment_type="cash",
            )
            db.add(encounter)
            db.flush()

            with self.assertRaises(NoFreeBlankError):
                issue_next_blank(
                    db,
                    blank_type=DRIVER,
                    client_id=client.id,
                    center_id=1,
                    encounter_id=encounter.id,
                )

            self._add_stock_batch(db, "40", (7,))
            issued = issue_next_blank(
                db,
                blank_type=DRIVER,
                client_id=client.id,
                center_id=1,
                encounter_id=encounter.id,
            )
            self.assertEqual(issued.full_number, "400000007")


if __name__ == "__main__":
    unittest.main()
