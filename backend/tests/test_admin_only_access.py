"""Учетные записи сотрудников, отчеты и касса доступны только админу.

Председатель заходит в программу постоянно, но ни добавлять пользователей, ни видеть
отчеты и кассу он не должен. Тесты проверяют и саму проверку роли, и то, что ею
закрыты все маршруты трех разделов: без этого новый маршрут остался бы открытым.
"""

from pathlib import Path
import sys
import unittest

from fastapi import HTTPException
from fastapi.routing import APIRoute
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes import auth as auth_routes  # noqa: E402
from app.api.v1.routes import payments as payments_routes  # noqa: E402
from app.api.v1.routes import reports as reports_routes  # noqa: E402
from app.api.v1.routes import staff as staff_routes  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.user import Role, User  # noqa: E402
from app.schemas.user_admin import StaffUserCreate  # noqa: E402


def _dependency_calls(dependant) -> set:
    calls = set()
    for child in dependant.dependencies:
        calls.add(child.call)
        calls |= _dependency_calls(child)
    return calls


class AdminOnlyAccessTests(unittest.TestCase):
    ROLE_CODES = ("chairman", "admin", "doctor", "operator")

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        with self.Session() as db:
            roles = {code: Role(code=code, name=code) for code in self.ROLE_CODES}
            db.add_all(roles.values())
            db.flush()
            db.add_all(
                User(
                    role_id=roles[code].id,
                    login=code,
                    password_hash=hash_password(f"{code}123"),
                    full_name=f"Сотрудник {code}",
                    is_active=True,
                )
                for code in self.ROLE_CODES
            )
            db.commit()

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _user(self, db, login: str) -> User:
        return db.execute(select(User).where(User.login == login)).scalar_one()

    def test_only_admin_passes_the_admin_check(self):
        with self.Session() as db:
            self.assertEqual(auth_routes.require_admin(current_user=self._user(db, "admin")).login, "admin")
            for login in ("chairman", "doctor", "operator"):
                with self.assertRaises(HTTPException) as raised:
                    auth_routes.require_admin(current_user=self._user(db, login))
                self.assertEqual(raised.exception.status_code, 403, login)

    def test_every_staff_report_and_payment_route_requires_admin(self):
        for module in (staff_routes, reports_routes, payments_routes):
            routes = [route for route in module.router.routes if isinstance(route, APIRoute)]
            self.assertTrue(routes, module.__name__)
            for route in routes:
                self.assertIn(
                    auth_routes.require_admin,
                    _dependency_calls(route.dependant),
                    f"{module.__name__}: {sorted(route.methods)} {route.path} открыт не только админу",
                )

    def test_admin_creates_and_deletes_staff_but_not_chairman_or_self(self):
        with self.Session() as db:
            center = Center(code="center-a", name="Центр")
            db.add(center)
            db.flush()
            payload = StaffUserCreate(
                login="new", password="temp12345", full_name="Новый", role_code="doctor", center_id=center.id
            )
            admin = self._user(db, "admin")
            created = staff_routes.create_staff(payload=payload, current_user=admin, db=db)
            self.assertEqual(created.login, "new")

            staff_routes.delete_staff_user(user_id=created.id, current_user=admin, db=db)
            self.assertIsNone(db.execute(select(User).where(User.login == "new")).scalar_one_or_none())

            for protected in (self._user(db, "chairman"), admin):
                with self.assertRaises(HTTPException) as raised:
                    staff_routes.delete_staff_user(user_id=protected.id, current_user=admin, db=db)
                self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
