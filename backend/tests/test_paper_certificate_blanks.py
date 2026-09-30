from pathlib import Path
import re
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
    BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE,
    BlankBatch,
    BlankForm,
    BlankType,
)
from app.services.blank_forms import (  # noqa: E402
    BLANK_VIEW_PAPER_CERTIFICATES,
    PAPER_CERTIFICATE_SERIES,
    create_auto_number_form,
    enrich_form_for_read,
    list_batches,
    list_forms,
    list_forms_page,
    stats,
)


DRIVER = BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE


class PaperCertificateBlanksTests(unittest.TestCase):
    """Справки на бумаге (ГТО, 095у…) показываются отдельно от бланков ВУ."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _seed(self, db):
        db.add_all(
            [
                BlankType(code=DRIVER, name="Водительская", is_active=True),
                BlankType(code=BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE, name="ГИМС", is_active=True),
            ]
        )
        db.flush()
        # Бланки ВУ из заведённой партии, серия «ГТО» у настоящей партии не делает её справкой.
        batch = BlankBatch(
            center_id=1, blank_type=DRIVER, series="40", number_from=1, number_to=2, number_width=7, quantity=2
        )
        odd_batch = BlankBatch(
            center_id=1, blank_type=DRIVER, series="ГТО", number_from=500, number_to=500, number_width=7, quantity=1
        )
        db.add_all([batch, odd_batch])
        db.flush()
        for number, series, owner in ((1, "40", batch), (2, "40", batch), (500, "ГТО", odd_batch)):
            db.add(
                BlankForm(
                    batch_id=owner.id,
                    center_id=1,
                    blank_type=DRIVER,
                    series=series,
                    number_value=number,
                    full_number=f"{series}{number:07d}",
                    status=BLANK_STATUS_FREE,
                )
            )
        db.flush()
        auto = {}
        for series in ("41", "ГТО", "095У", "070у"):
            form = create_auto_number_form(db, blank_type=DRIVER, center_id=1, series=series)
            form.status = BLANK_STATUS_ISSUED
            auto[series] = form
        db.flush()
        return auto

    def test_driver_list_holds_only_driver_blanks(self):
        with self.Session() as db:
            self._seed(db)

            numbers = {form.full_number for form in list_forms(db, blank_type=DRIVER)}

            # Партия «ГТО» из заведённых — бланк ВУ; автономер «41» — печать ВУ со старой серией.
            self.assertEqual(numbers, {"400000001", "400000002", "ГТО0000500", "410000001"})

    def test_paper_view_holds_only_auto_numbered_certificates(self):
        with self.Session() as db:
            self._seed(db)

            numbers = {form.full_number for form in list_forms(db, blank_type=BLANK_VIEW_PAPER_CERTIFICATES)}

            self.assertEqual(numbers, {"ГТО0000002", "095У0000003", "070у0000004"})

    def test_page_counts_follow_the_split(self):
        with self.Session() as db:
            self._seed(db)

            _, driver_total = list_forms_page(db, blank_type=DRIVER, status=BLANK_STATUS_ISSUED)
            _, paper_total = list_forms_page(db, blank_type=BLANK_VIEW_PAPER_CERTIFICATES, status=BLANK_STATUS_ISSUED)
            _, all_total = list_forms_page(db, status=BLANK_STATUS_ISSUED)

            self.assertEqual((driver_total, paper_total, all_total), (1, 3, 4))

    def test_stats_show_paper_certificates_as_their_own_row(self):
        with self.Session() as db:
            self._seed(db)

            rows = {row["blank_type"]: row for row in stats(db, center_id=1)}

            self.assertEqual(rows[DRIVER]["issued"], 1)
            self.assertEqual(rows[DRIVER]["free"], 3)
            self.assertEqual(rows[DRIVER]["total"], 4)
            paper = rows[BLANK_VIEW_PAPER_CERTIFICATES]
            self.assertEqual((paper["total"], paper["issued"], paper["free"]), (3, 3, 0))
            self.assertEqual(paper["blank_type_name"], "Справки на бумаге")
            self.assertEqual(list(rows)[:2], [DRIVER, BLANK_VIEW_PAPER_CERTIFICATES])

    def test_batches_are_split_the_same_way(self):
        with self.Session() as db:
            self._seed(db)

            driver = {(batch.series) for batch, _counts in list_batches(db, blank_type=DRIVER)}
            paper = {(batch.series) for batch, _counts in list_batches(db, blank_type=BLANK_VIEW_PAPER_CERTIFICATES)}

            self.assertEqual(driver, {"40", "ГТО", "41"})
            self.assertEqual(paper, {"ГТО", "095У", "070у"})

    def test_read_payload_marks_paper_certificates(self):
        with self.Session() as db:
            auto = self._seed(db)
            strict_gto = db.query(BlankForm).filter(BlankForm.full_number == "ГТО0000500").one()

            self.assertTrue(enrich_form_for_read(db, auto["095У"])["is_paper_certificate"])
            self.assertTrue(enrich_form_for_read(db, auto["070у"])["is_paper_certificate"])
            self.assertFalse(enrich_form_for_read(db, auto["41"])["is_paper_certificate"])
            self.assertFalse(enrich_form_for_read(db, strict_gto)["is_paper_certificate"])


    def test_series_list_follows_the_print_window_series(self):
        """Серия справки, добавленная в окно печати, должна попасть и в этот список."""

        app_js = Path(__file__).resolve().parents[2] / "frontend" / "public" / "demo" / "app.js"
        source = app_js.read_text(encoding="utf-8")

        def quoted(block_start: str, block_end: str) -> list[str]:
            start = source.index(block_start)
            return re.findall(r'"([^"]+)"', source[start : source.index(block_end, start)])

        window_series = quoted("const CERTIFICATE_PRINT_SERIES_OPTIONS = [", "];")
        auto_create_series = quoted("const CHAIRMAN_AUTO_CREATE_BLANK_SERIES = new Set([", "]);")
        # ЛМК, ГИМС и 4026 — отдельные типы бланков, не справки на бумаге.
        own_types = {"ЛМК", "ГИМС", "4026"}

        known = set(PAPER_CERTIFICATE_SERIES)
        missing = sorted({s for s in window_series + auto_create_series if s not in own_types and s not in known})
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
