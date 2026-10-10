"""Клиенты из старого Excel должны попадать в медцентр, иначе их не видит ни один сотрудник."""

import importlib.util
import os
from pathlib import Path
import sys
import unittest
from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


os.environ.setdefault("ALLOW_SQLITE", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "import_legacy_excel.py"


def load_import_script():
    spec = importlib.util.spec_from_file_location("import_legacy_excel", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def legacy_row(patient_number, last_name):
    return {"patient_number": patient_number, "last_name": last_name, "first_name": "Иван", "birth_date": date(1980, 1, 1)}


class LegacyExcelImportCenterTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.script = load_import_script()

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_new_client_goes_to_the_first_center(self):
        with self.Session() as db:
            db.add_all([Center(code="center-a", name="Мед-Авто"), Center(code="center-b", name="Медилэнд")])
            db.commit()
            first_center = db.execute(select(Center).order_by(Center.id)).scalars().first()

            self.script.upsert_clients(db, [legacy_row(1, "Иванов")])

            client = db.execute(select(Client)).scalars().one()
            self.assertEqual(client.center_ids, [first_center.id])

    def test_existing_client_keeps_its_centers(self):
        with self.Session() as db:
            db.add_all([Center(code="center-a", name="Мед-Авто"), Center(code="center-b", name="Медилэнд")])
            db.commit()
            second_center = db.execute(select(Center).order_by(Center.id.desc())).scalars().first()
            db.add(Client(patient_number=1, last_name="Петров", first_name="Пётр", birth_date=date(1975, 3, 3), centers=[second_center]))
            db.commit()

            self.script.upsert_clients(db, [legacy_row(1, "Петров")])

            client = db.execute(select(Client)).scalars().one()
            self.assertEqual(client.center_ids, [second_center.id])


if __name__ == "__main__":
    unittest.main()
