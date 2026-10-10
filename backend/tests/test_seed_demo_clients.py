"""Демо-клиенты, которых заводит seed на пустой базе, должны лежать в базе центра.

Клиент без центра не виден ни одному сотруднику, и демо-клиент пропадал из журнала.
"""

import os
from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


os.environ.setdefault("ALLOW_SQLITE", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.services.seed import seed_reference_data  # noqa: E402


class SeedDemoClientsTests(unittest.TestCase):
    def test_demo_clients_belong_to_the_first_center(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        try:
            with Session() as db:
                seed_reference_data(db)
                db.commit()

                first_center = db.execute(select(Center).order_by(Center.id.asc())).scalars().first()
                clients = db.execute(select(Client)).scalars().all()

                self.assertTrue(clients)
                for client in clients:
                    self.assertEqual(client.center_ids, [first_center.id], client.last_name)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
