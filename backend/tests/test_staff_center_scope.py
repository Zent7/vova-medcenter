"""Сотрудник работает в своих медцентрах, админ видит все.

Центры выбирают при создании учётной записи и меняют потом: первый основной, с
него сотрудник начинает работу, остальные дополнительные. Вход возвращает список
интерфейсу, и тот оставляет в переключателе только эти центры. Админу центры не
нужны: он видит все, даже если в базе у него записан какой-то один.
"""

from pathlib import Path
import sys
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes import auth as auth_routes  # noqa: E402
from app.api.v1.routes import staff as staff_routes  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.user import Role, User, user_extra_centers  # noqa: E402
from app.schemas.auth import LoginRequest  # noqa: E402
from app.schemas.user_admin import StaffCentersUpdate, StaffUserCreate  # noqa: E402


class StaffCenterScopeTests(unittest.TestCase):
    ROLE_CODES = ("chairman", "admin", "doctor", "operator")

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.original_session_local = auth_routes.SessionLocal
        auth_routes.SessionLocal = self.Session

        with self.Session() as db:
            first = Center(code="center-a", name="Первый центр")
            second = Center(code="center-b", name="Второй центр")
            closed = Center(code="center-x", name="Закрытый центр", is_active=False)
            db.add_all([first, second, closed])
            roles = {code: Role(code=code, name=code) for code in self.ROLE_CODES}
            db.add_all(roles.values())
            db.flush()
            self.first_id, self.second_id, self.closed_id = first.id, second.id, closed.id
            # Админ из сида записан в первый центр, но видит все.
            db.add_all(
                [
                    User(
                        role_id=roles["admin"].id,
                        center_id=first.id,
                        login="admin",
                        password_hash=hash_password("admin123"),
                        full_name="Админ",
                    ),
                    User(
                        role_id=roles["operator"].id,
                        center_id=second.id,
                        login="operator",
                        password_hash=hash_password("operator123"),
                        full_name="Оператор второго центра",
                    ),
                    User(
                        role_id=roles["chairman"].id,
                        center_id=first.id,
                        login="chairman",
                        password_hash=hash_password("chairman123"),
                        full_name="Председатель",
                    ),
                ]
            )
            db.commit()

    def tearDown(self):
        auth_routes.SessionLocal = self.original_session_local
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _admin(self, db) -> User:
        return db.execute(select(User).where(User.login == "admin")).scalar_one()

    def _create(self, db, **overrides):
        values = {"login": "new", "password": "temp12345", "full_name": "Новый", "role_code": "doctor"}
        values.update(overrides)
        return staff_routes.create_staff(payload=StaffUserCreate(**values), current_user=self._admin(db), db=db)

    def test_doctor_is_pinned_to_the_chosen_center(self):
        with self.Session() as db:
            created = self._create(db, center_id=self.second_id)

            self.assertEqual(created.center_id, self.second_id)
            self.assertEqual(created.center_name, "Второй центр")
            self.assertFalse(created.all_centers)
            stored = db.execute(select(User).where(User.login == "new")).scalar_one()
            self.assertEqual(stored.center_id, self.second_id)

    def test_center_is_required_for_everyone_but_the_admin(self):
        with self.Session() as db:
            for role_code in ("doctor", "operator"):
                with self.assertRaises(HTTPException) as raised:
                    self._create(db, role_code=role_code)
                self.assertEqual(raised.exception.status_code, 400, role_code)
                self.assertEqual(raised.exception.detail, "Выберите медцентр сотрудника")
            self.assertIsNone(db.execute(select(User).where(User.login == "new")).scalar_one_or_none())

    def test_unknown_or_closed_center_is_refused(self):
        with self.Session() as db:
            for center_id in (9999, self.closed_id):
                with self.assertRaises(HTTPException) as raised:
                    self._create(db, center_id=center_id)
                self.assertEqual(raised.exception.status_code, 400, center_id)
                self.assertEqual(raised.exception.detail, "Медцентр не найден")

    def test_new_admin_gets_no_center_and_sees_all(self):
        with self.Session() as db:
            created = self._create(db, role_code="admin", center_id=self.second_id)

            self.assertIsNone(created.center_id)
            self.assertIsNone(created.center_name)
            self.assertTrue(created.all_centers)
            stored = db.execute(select(User).where(User.login == "new")).scalar_one()
            self.assertIsNone(stored.center_id)

    def test_login_returns_the_pinned_center(self):
        response = auth_routes.login(LoginRequest(login="operator", password="operator123"))

        self.assertEqual(response.center_id, self.second_id)
        self.assertEqual(response.center_name, "Второй центр")
        self.assertFalse(response.all_centers)

    def test_chairman_is_pinned_like_any_other_employee(self):
        response = auth_routes.login(LoginRequest(login="chairman", password="chairman123"))

        self.assertEqual(response.center_id, self.first_id)
        self.assertFalse(response.all_centers)

    def test_admin_login_sees_all_centers_even_with_a_stored_center(self):
        response = auth_routes.login(LoginRequest(login="admin", password="admin123"))

        self.assertIsNone(response.center_id)
        self.assertIsNone(response.center_name)
        self.assertTrue(response.all_centers)

    def test_staff_list_shows_where_everyone_works(self):
        with self.Session() as db:
            listed = {user.login: user for user in staff_routes.list_staff(_=self._admin(db), db=db)}

        self.assertEqual(listed["operator"].center_name, "Второй центр")
        self.assertFalse(listed["operator"].all_centers)
        self.assertTrue(listed["admin"].all_centers)
        self.assertIsNone(listed["admin"].center_name)

    def _third_center_id(self, db) -> int:
        third = Center(code="center-c", name="Третий центр")
        db.add(third)
        db.flush()
        return third.id

    def _center_names(self, user) -> list[str]:
        return [center.name for center in user.centers]

    def test_employee_can_work_in_several_centers_the_first_is_main(self):
        with self.Session() as db:
            created = self._create(db, center_ids=[self.second_id, self.first_id])

            self.assertEqual(created.center_id, self.second_id)
            self.assertEqual(created.center_name, "Второй центр")
            self.assertEqual(self._center_names(created), ["Второй центр", "Первый центр"])
            stored = db.execute(select(User).where(User.login == "new")).scalar_one()
            self.assertEqual(stored.center_id, self.second_id)
            self.assertEqual([center.id for center in stored.extra_centers], [self.first_id])

    def test_repeated_centers_are_stored_once(self):
        with self.Session() as db:
            created = self._create(db, center_ids=[self.first_id, self.second_id, self.first_id])

            self.assertEqual(self._center_names(created), ["Первый центр", "Второй центр"])
            links = db.execute(select(user_extra_centers)).all()
            self.assertEqual(len(links), 1)

    def test_every_listed_center_must_exist_and_be_open(self):
        with self.Session() as db:
            for center_ids in ([self.first_id, 9999], [self.second_id, self.closed_id]):
                with self.assertRaises(HTTPException) as raised:
                    self._create(db, center_ids=center_ids)
                self.assertEqual(raised.exception.detail, "Медцентр не найден", center_ids)
            with self.assertRaises(HTTPException) as raised:
                self._create(db, center_ids=[])
            self.assertEqual(raised.exception.detail, "Выберите медцентр сотрудника")
            self.assertIsNone(db.execute(select(User).where(User.login == "new")).scalar_one_or_none())

    def test_single_center_id_of_an_older_page_still_works(self):
        with self.Session() as db:
            created = self._create(db, center_id=self.second_id)

            self.assertEqual(self._center_names(created), ["Второй центр"])
            self.assertEqual(db.execute(select(user_extra_centers)).all(), [])

    def test_admin_gets_no_centers_even_when_some_are_sent(self):
        with self.Session() as db:
            created = self._create(db, role_code="admin", center_ids=[self.first_id, self.second_id])

            self.assertEqual(created.centers, [])
            self.assertTrue(created.all_centers)
            self.assertEqual(db.execute(select(user_extra_centers)).all(), [])

    def test_login_returns_every_center_with_the_main_one_first(self):
        with self.Session() as db:
            self._create(db, center_ids=[self.second_id, self.first_id])

        response = auth_routes.login(LoginRequest(login="new", password="temp12345"))

        self.assertEqual(response.center_id, self.second_id)
        self.assertEqual([center.name for center in response.centers], ["Второй центр", "Первый центр"])
        self.assertFalse(response.all_centers)

    def test_login_of_single_center_employee_and_admin(self):
        operator = auth_routes.login(LoginRequest(login="operator", password="operator123"))
        admin = auth_routes.login(LoginRequest(login="admin", password="admin123"))

        self.assertEqual([center.name for center in operator.centers], ["Второй центр"])
        self.assertEqual(admin.centers, [])

    def test_staff_list_shows_every_center_of_everyone(self):
        with self.Session() as db:
            self._create(db, center_ids=[self.first_id, self.second_id])
            listed = {user.login: user for user in staff_routes.list_staff(_=self._admin(db), db=db)}

        self.assertEqual(self._center_names(listed["new"]), ["Первый центр", "Второй центр"])
        self.assertEqual(self._center_names(listed["operator"]), ["Второй центр"])
        self.assertEqual(listed["admin"].centers, [])

    def _update(self, db, login, center_ids):
        user = db.execute(select(User).where(User.login == login)).scalar_one()
        return staff_routes.update_staff_centers(
            user_id=user.id, payload=StaffCentersUpdate(center_ids=center_ids), _=self._admin(db), db=db
        )

    def test_existing_employee_gets_more_centers_and_has_to_sign_in_again(self):
        with self.Session() as db:
            before = db.execute(select(User).where(User.login == "operator")).scalar_one().session_epoch

            updated = self._update(db, "operator", [self.second_id, self.first_id])

            self.assertEqual(updated.center_id, self.second_id)
            self.assertEqual(self._center_names(updated), ["Второй центр", "Первый центр"])
            after = db.execute(select(User).where(User.login == "operator")).scalar_one().session_epoch
            self.assertNotEqual(before, after)

    def test_changing_the_main_center_and_taking_one_away(self):
        with self.Session() as db:
            third_id = self._third_center_id(db)
            self._update(db, "operator", [self.second_id, self.first_id, third_id])

            switched = self._update(db, "operator", [third_id, self.second_id])
            self.assertEqual(switched.center_id, third_id)
            self.assertEqual(self._center_names(switched), ["Третий центр", "Второй центр"])

            narrowed = self._update(db, "operator", [self.second_id])
            self.assertEqual(self._center_names(narrowed), ["Второй центр"])
            self.assertEqual(db.execute(select(user_extra_centers)).all(), [])

    def test_unchanged_centers_keep_the_session(self):
        with self.Session() as db:
            before = db.execute(select(User).where(User.login == "operator")).scalar_one().session_epoch

            self._update(db, "operator", [self.second_id])

            after = db.execute(select(User).where(User.login == "operator")).scalar_one().session_epoch
            self.assertEqual(before, after)

    def test_update_refuses_admin_unknown_user_and_bad_centers(self):
        with self.Session() as db:
            with self.assertRaises(HTTPException) as raised:
                self._update(db, "admin", [self.first_id])
            self.assertEqual(raised.exception.status_code, 400)

            with self.assertRaises(HTTPException) as raised:
                staff_routes.update_staff_centers(
                    user_id=9999, payload=StaffCentersUpdate(center_ids=[self.first_id]), _=self._admin(db), db=db
                )
            self.assertEqual(raised.exception.status_code, 404)

            for center_ids, detail in (
                ([], "Выберите медцентр сотрудника"),
                ([self.second_id, self.closed_id], "Медцентр не найден"),
            ):
                with self.assertRaises(HTTPException) as raised:
                    self._update(db, "operator", center_ids)
                self.assertEqual(raised.exception.detail, detail)

            operator = db.execute(select(User).where(User.login == "operator")).scalar_one()
            self.assertEqual(operator.center_id, self.second_id)

    def test_chairman_can_be_given_several_centers_like_anyone(self):
        with self.Session() as db:
            updated = self._update(db, "chairman", [self.first_id, self.second_id])

            self.assertEqual(self._center_names(updated), ["Первый центр", "Второй центр"])

    def test_deleting_an_employee_drops_the_extra_center_links(self):
        with self.Session() as db:
            created = self._create(db, center_ids=[self.first_id, self.second_id])
            self.assertEqual(len(db.execute(select(user_extra_centers)).all()), 1)

            staff_routes.delete_staff_user(user_id=created.id, current_user=self._admin(db), db=db)

            self.assertEqual(db.execute(select(user_extra_centers)).all(), [])


if __name__ == "__main__":
    unittest.main()
