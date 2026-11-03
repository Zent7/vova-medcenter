"""Бланки отдают только медцентры, в которых работает сотрудник.

Врач, председатель и оператор получают списки, остатки и номера бланков своих медцентров
(основного и дополнительных). Чужой центр и отсутствие центра дают 403. Админ видит все
центры. Тест на маршруты ловит новый GET с центром, если в нем забыли проверку.
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
from app.api.v1.routes import blanks as blanks_routes  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.blank_form import BLANK_STATUS_FREE, NUMBERED_BLANK_TYPES, BlankBatch, BlankForm  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.user import Role, User  # noqa: E402


DRIVER_TYPE = NUMBERED_BLANK_TYPES[0][0]


def _dependency_calls(dependant) -> set:
    calls = set()
    for child in dependant.dependencies:
        calls.add(child.call)
        calls |= _dependency_calls(child)
    return calls


class BlankCenterAccessTests(unittest.TestCase):
    ROLE_CODES = ("admin", "chairman", "doctor", "operator")

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

    def _seed(self, db) -> dict[str, Center]:
        # Врач работает в «own» и «extra», председатель и оператор только в «own»,
        # «foreign» никому из них не назначен. Серия каждого центра называется по его ключу.
        centers = {
            "own": Center(code="center-a", name="Центр А"),
            "extra": Center(code="center-b", name="Центр Б"),
            "foreign": Center(code="center-c", name="Центр В"),
        }
        db.add_all(centers.values())
        db.flush()
        doctor = self._user(db, "doctor")
        doctor.center = centers["own"]
        doctor.extra_centers = [centers["extra"]]
        self._user(db, "chairman").center = centers["own"]
        self._user(db, "operator").center = centers["own"]

        for key, center in centers.items():
            series = key.upper()
            batch = BlankBatch(
                center_id=center.id,
                blank_type=DRIVER_TYPE,
                series=series,
                number_from=1,
                number_to=2,
                number_width=6,
                quantity=2,
            )
            db.add(batch)
            db.flush()
            db.add_all(
                BlankForm(
                    batch_id=batch.id,
                    center_id=center.id,
                    blank_type=DRIVER_TYPE,
                    series=series,
                    number_value=value,
                    full_number=f"{series}{value:06d}",
                    status=BLANK_STATUS_FREE,
                )
                for value in (1, 2)
            )
        db.commit()
        return centers

    def _list_calls(self, db, user, center_id, series: str):
        """Каждый GET бланков с центром — отдельным вызовом, как его зовет фронтенд."""

        return {
            "series": lambda: blanks_routes.get_free_series(
                blank_type=DRIVER_TYPE, center_id=center_id, strict_only=False, db=db, current_user=user
            ),
            "batches": lambda: blanks_routes.get_batches(
                blank_type=None, center_id=center_id, db=db, current_user=user
            ),
            "forms": lambda: blanks_routes.get_forms(
                blank_type=None,
                batch_id=None,
                blank_status=None,
                center_id=center_id,
                search=None,
                limit=200,
                db=db,
                current_user=user,
            ),
            "forms/page": lambda: blanks_routes.get_forms_page(
                blank_type=None,
                batch_id=None,
                blank_status=None,
                center_id=center_id,
                search=None,
                limit=50,
                offset=0,
                db=db,
                current_user=user,
            ),
            "forms/next": lambda: blanks_routes.get_next_form(
                blank_type=DRIVER_TYPE,
                center_id=center_id,
                series=None,
                auto_create=False,
                strict_only=False,
                batch_part_id=None,
                db=db,
                current_user=user,
            ),
            "forms/exact": lambda: blanks_routes.get_exact_form(
                blank_type=DRIVER_TYPE,
                center_id=center_id,
                series=series,
                number="000001",
                strict_only=False,
                batch_part_id=None,
                db=db,
                current_user=user,
            ),
            "stats": lambda: blanks_routes.get_stats(center_id=center_id, db=db, current_user=user),
        }

    def test_doctor_is_refused_lists_of_foreign_or_missing_center(self):
        with self.Session() as db:
            centers = self._seed(db)
            doctor = self._user(db, "doctor")
            for center_id in (centers["foreign"].id, None):
                for name, call in self._list_calls(db, doctor, center_id, series="FOREIGN").items():
                    with self.subTest(center_id=center_id, route=name):
                        with self.assertRaises(HTTPException) as raised:
                            call()
                        self.assertEqual(raised.exception.status_code, 403)

    def test_doctor_sees_own_and_extra_centers(self):
        with self.Session() as db:
            centers = self._seed(db)
            doctor = self._user(db, "doctor")
            for key in ("own", "extra"):
                center = centers[key]
                with self.subTest(center=key):
                    batches = blanks_routes.get_batches(blank_type=None, center_id=center.id, db=db, current_user=doctor)
                    self.assertEqual([batch.series for batch in batches], [key.upper()])

                    page = blanks_routes.get_forms_page(
                        blank_type=None,
                        batch_id=None,
                        blank_status=None,
                        center_id=center.id,
                        search=None,
                        limit=50,
                        offset=0,
                        db=db,
                        current_user=doctor,
                    )
                    self.assertEqual(page.total, 2)
                    self.assertTrue(all(item.center_id == center.id for item in page.items))

                    for name, call in self._list_calls(db, doctor, center.id, series=key.upper()).items():
                        with self.subTest(route=name):
                            call()

    def test_operator_and_chairman_are_limited_to_their_own_center(self):
        with self.Session() as db:
            centers = self._seed(db)
            for login in ("operator", "chairman"):
                user = self._user(db, login)
                with self.subTest(login=login):
                    form = blanks_routes.get_next_form(
                        blank_type=DRIVER_TYPE,
                        center_id=centers["own"].id,
                        series=None,
                        auto_create=False,
                        strict_only=False,
                        batch_part_id=None,
                        db=db,
                        current_user=user,
                    )
                    self.assertEqual(form.series, "OWN")
                    with self.assertRaises(HTTPException) as raised:
                        blanks_routes.get_batches(blank_type=None, center_id=centers["extra"].id, db=db, current_user=user)
                    self.assertEqual(raised.exception.status_code, 403)

    def test_admin_sees_every_center(self):
        with self.Session() as db:
            centers = self._seed(db)
            admin = self._user(db, "admin")

            batches = blanks_routes.get_batches(blank_type=None, center_id=None, db=db, current_user=admin)
            self.assertEqual({batch.series for batch in batches}, {"OWN", "EXTRA", "FOREIGN"})

            for name, call in self._list_calls(db, admin, centers["foreign"].id, series="FOREIGN").items():
                with self.subTest(route=name):
                    call()

    def test_every_blank_get_with_center_checks_the_user(self):
        routes = [
            route
            for route in blanks_routes.router.routes
            if isinstance(route, APIRoute) and "GET" in route.methods
        ]
        with_center = [
            route for route in routes if "center_id" in {param.name for param in route.dependant.query_params}
        ]
        self.assertGreaterEqual(len(with_center), 7)
        for route in with_center:
            self.assertIn(
                auth_routes.get_optional_current_user,
                _dependency_calls(route.dependant),
                f"GET {route.path} принимает center_id, но не проверяет его по сотруднику",
            )


if __name__ == "__main__":
    unittest.main()
