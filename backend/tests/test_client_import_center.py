"""Загрузка клиентов заводит обращения в медцентре оператора.

Раньше медцентр брался у системного пользователя и по факту всегда оказывался
первым: оператор третьего центра грузил свой список, а обращения уезжали чужому
центру — вместе с кассой, календарём повторов и отчётами.
"""

from pathlib import Path
import os
import sys
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


os.environ.setdefault("ALLOW_SQLITE", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.imports import get_import_center  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.user import Role, User  # noqa: E402


class ClientImportCenterTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

        with self.Session() as db:
            first = Center(code="center-a", name="Медцентр 1")
            second = Center(code="center-b", name="Медцентр 2")
            third = Center(code="center-c", name="Медцентр 3")
            role = Role(code="admin", name="Администратор")
            db.add_all([first, second, third, role])
            db.flush()
            self.first, self.second, self.third = first.id, second.id, third.id

            actor = User(
                center_id=first.id,
                role_id=role.id,
                login="system",
                password_hash="x",
                full_name="Система",
                is_active=True,
            )
            db.add(actor)
            db.flush()
            self.actor_id = actor.id
            db.commit()

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_center_from_the_request_wins(self):
        with self.Session() as db:
            center = get_import_center(db, self.actor_id, self.third)
            self.assertEqual(center.id, self.third)

    def test_falls_back_to_the_actor_center_without_a_request_center(self):
        with self.Session() as db:
            center = get_import_center(db, self.actor_id, None)
            self.assertEqual(center.id, self.first)

    def test_unknown_center_does_not_silently_import_elsewhere(self):
        with self.Session() as db:
            # Несуществующий центр — падаем обратно на центр пользователя, а не
            # тихо принимаем чужой идентификатор.
            center = get_import_center(db, self.actor_id, 9999)
            self.assertEqual(center.id, self.first)

    def test_inactive_center_is_not_used(self):
        with self.Session() as db:
            disabled = db.get(Center, self.second)
            disabled.is_active = False
            db.commit()

            center = get_import_center(db, self.actor_id, self.second)
            self.assertEqual(center.id, self.first)


if __name__ == "__main__":
    unittest.main()
