"""Третий медцентр должен появиться и у уже работающей установки.

Раньше центры заводились только на пустой базе, поэтому новый медцентр не
доезжал до боевой базы, где центры уже есть. Переключатель центров в интерфейсе
подбирает центр по названию, поэтому справочник в backend, список в app.js и
варианты в index.html обязаны совпадать.
"""

from pathlib import Path
import re
import sys
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.services.seed import WORKSPACE_CENTERS, _ensure_workspace_centers  # noqa: E402


DEMO_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public" / "demo"


class WorkspaceCentersTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _codes_and_names(self, db):
        centers = db.execute(select(Center).order_by(Center.id.asc())).scalars().all()
        return [(center.code, center.name) for center in centers]

    def test_three_centers_are_created_on_an_empty_database(self):
        with self.Session() as db:
            _ensure_workspace_centers(db)
            db.commit()

            self.assertEqual(self._codes_and_names(db), WORKSPACE_CENTERS)
            self.assertTrue(all(center.is_active for center in db.execute(select(Center)).scalars()))

    def test_missing_center_is_added_to_an_existing_installation(self):
        with self.Session() as db:
            db.add(Center(code="center-a", name="Медцентр 1"))
            db.add(Center(code="center-b", name="Медцентр 2"))
            db.commit()

            _ensure_workspace_centers(db)
            db.commit()

            self.assertEqual(self._codes_and_names(db), WORKSPACE_CENTERS)

    def test_existing_center_keeps_its_own_name_and_details(self):
        with self.Session() as db:
            db.add(Center(code="center-a", name="Переименованный центр", inn="7712345678"))
            db.commit()

            _ensure_workspace_centers(db)
            db.commit()

            renamed = db.execute(select(Center).where(Center.code == "center-a")).scalar_one()
            self.assertEqual(renamed.name, "Переименованный центр")
            self.assertEqual(renamed.inn, "7712345678")

    def test_repeated_startup_does_not_duplicate_centers(self):
        with self.Session() as db:
            for _ in range(3):
                _ensure_workspace_centers(db)
                db.commit()

            self.assertEqual(self._codes_and_names(db), WORKSPACE_CENTERS)

    def test_demo_ui_offers_the_centers_the_backend_creates(self):
        """Список в интерфейсе — начало списка центров базы, имя в имя.

        Он может быть короче: центр бывает заведён, но ещё не введён в работу и
        скрыт от оператора. А вот разойтись в названии или порядке они не имеют
        права — центр подбирается по названию, и переключатель просто перестал бы
        находить его в базе.
        """

        known_names = [name for _, name in WORKSPACE_CENTERS]

        app_js = (DEMO_DIR / "app.js").read_text(encoding="utf-8")
        names_line = re.search(r"const WORKSPACE_CENTER_NAMES = \[(.*?)\];", app_js, re.S)
        self.assertIsNotNone(names_line, "WORKSPACE_CENTER_NAMES не найден в app.js")
        visible_names = re.findall(r'"([^"]+)"', names_line.group(1))

        self.assertTrue(visible_names, "В переключателе должен остаться хотя бы один медцентр")
        self.assertEqual(
            visible_names,
            known_names[: len(visible_names)],
            "Список медцентров в app.js разошёлся со справочником backend",
        )

        index_html = (DEMO_DIR / "index.html").read_text(encoding="utf-8")
        select_block = re.search(r'<select[^>]*id="centerSelect".*?</select>', index_html, re.S)
        self.assertIsNotNone(select_block, "Переключатель centerSelect не найден в index.html")
        self.assertEqual(
            re.findall(r"<option[^>]*>([^<]+)</option>", select_block.group(0)),
            visible_names,
            "Варианты в index.html разошлись с WORKSPACE_CENTER_NAMES",
        )


if __name__ == "__main__":
    unittest.main()
