"""График сотрудника: смена, время «со скольки – до скольки» и ставка часа.

Задаётся при создании учетной записи, потом меняется кнопкой «График» у существующего
сотрудника (`PUT /staff/{id}/schedule`) и возвращается в списке сотрудников. Смену можно
выбрать только из пяти вариантов, время и ставка проверяются. Без графика все поля пустые.
"""

from datetime import time
from decimal import Decimal
from pathlib import Path
import sys
import unittest

from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes import staff as staff_routes  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.user import Role, User  # noqa: E402
from app.schemas.user_admin import StaffScheduleUpdate, StaffUserCreate  # noqa: E402


def staff_payload(**overrides) -> dict:
    values = {
        "login": "new",
        "password": "temp12345",
        "full_name": "Новый сотрудник",
        "role_code": "doctor",
        "center_ids": [1],
    }
    values.update(overrides)
    return values


def schedule(**overrides) -> dict:
    values = {"pattern": "2/2", "shift_start": "08:00", "shift_end": "20:00", "hourly_rate": "350"}
    values.update(overrides)
    return values


class StaffScheduleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        with self.Session() as db:
            center = Center(code="center-a", name="Первый центр")
            db.add(center)
            roles = {code: Role(code=code, name=code) for code in ("admin", "doctor")}
            db.add_all(roles.values())
            db.flush()
            self.center_id = center.id
            db.add(
                User(
                    role_id=roles["admin"].id,
                    login="admin",
                    password_hash=hash_password("admin123"),
                    full_name="Админ",
                )
            )
            db.commit()

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _admin(self, db) -> User:
        return db.execute(select(User).where(User.login == "admin")).scalar_one()

    def _create(self, db, login="new", **overrides):
        payload = StaffUserCreate(**staff_payload(login=login, center_ids=[self.center_id], **overrides))
        return staff_routes.create_staff(payload=payload, background_tasks=BackgroundTasks(), current_user=self._admin(db), db=db)

    def test_schedule_is_saved_and_returned(self):
        with self.Session() as db:
            created = self._create(db, schedule=schedule(hourly_rate="350.50"))

            self.assertEqual(created.schedule.pattern, "2/2")
            self.assertEqual(created.schedule.shift_start, time(8, 0))
            self.assertEqual(created.schedule.shift_end, time(20, 0))
            self.assertEqual(created.schedule.hourly_rate, Decimal("350.50"))
            stored = db.execute(select(User).where(User.login == "new")).scalar_one()
            self.assertEqual(stored.schedule_pattern, "2/2")
            self.assertEqual(stored.schedule_start, time(8, 0))
            self.assertEqual(stored.schedule_end, time(20, 0))

    def test_employee_created_without_schedule_has_none(self):
        with self.Session() as db:
            created = self._create(db)

            self.assertIsNone(created.schedule)
            stored = db.execute(select(User).where(User.login == "new")).scalar_one()
            self.assertIsNone(stored.schedule_pattern)
            self.assertIsNone(stored.schedule_start)
            self.assertIsNone(stored.hourly_rate)

    def test_rate_is_optional(self):
        with self.Session() as db:
            created = self._create(db, schedule=schedule(hourly_rate=None))

            self.assertEqual(created.schedule.pattern, "2/2")
            self.assertIsNone(created.schedule.hourly_rate)

    def test_night_shift_keeps_the_hours_as_entered(self):
        with self.Session() as db:
            created = self._create(db, schedule=schedule(shift_start="20:00", shift_end="08:00"))

            self.assertEqual(created.schedule.shift_start, time(20, 0))
            self.assertEqual(created.schedule.shift_end, time(8, 0))

    def test_schedule_is_listed_for_staff(self):
        with self.Session() as db:
            self._create(db, login="shifted", schedule=schedule(pattern="5/2"))
            self._create(db, login="plain")
            listed = {user.login: user for user in staff_routes.list_staff(_=self._admin(db), db=db)}

        self.assertEqual(listed["shifted"].schedule.pattern, "5/2")
        self.assertEqual(listed["shifted"].schedule.hourly_rate, Decimal("350"))
        self.assertIsNone(listed["plain"].schedule)

    def test_only_the_five_patterns_are_accepted(self):
        for pattern in ("2/2", "3/3", "4/4", "5/2", "6/1"):
            with self.subTest(pattern=pattern):
                created = StaffUserCreate(**staff_payload(schedule=schedule(pattern=pattern)))
                self.assertEqual(created.schedule.pattern, pattern)
        for pattern in ("1/1", "7/7", "2/3", "", "двое через двое"):
            with self.subTest(pattern=pattern), self.assertRaises(ValidationError):
                StaffUserCreate(**staff_payload(schedule=schedule(pattern=pattern)))

    def test_both_times_are_required_and_must_be_clock_times(self):
        for missing in ("shift_start", "shift_end"):
            values = schedule()
            del values[missing]
            with self.subTest(missing=missing), self.assertRaises(ValidationError):
                StaffUserCreate(**staff_payload(schedule=values))
        with self.assertRaises(ValidationError):
            StaffUserCreate(**staff_payload(schedule=schedule(shift_end="25:00")))

    def test_rate_cannot_be_negative_or_finer_than_kopecks(self):
        for rate in ("-1", "350.555"):
            with self.subTest(rate=rate), self.assertRaises(ValidationError):
                StaffUserCreate(**staff_payload(schedule=schedule(hourly_rate=rate)))

    def _update_schedule(self, db, login, schedule_values):
        user = db.execute(select(User).where(User.login == login)).scalar_one()
        payload = StaffScheduleUpdate(schedule=schedule_values)
        return staff_routes.update_staff_schedule(user_id=user.id, payload=payload, background_tasks=BackgroundTasks(), admin=self._admin(db), db=db)

    def test_admin_sets_schedule_of_existing_employee(self):
        with self.Session() as db:
            self._create(db, login="plain")

            updated = self._update_schedule(
                db, "plain", schedule(pattern="3/3", shift_start="07:30", shift_end="19:30", hourly_rate="420")
            )

            self.assertEqual(updated.schedule.pattern, "3/3")
            self.assertEqual(updated.schedule.shift_start, time(7, 30))
            self.assertEqual(updated.schedule.shift_end, time(19, 30))
            self.assertEqual(updated.schedule.hourly_rate, Decimal("420"))
            stored = db.execute(select(User).where(User.login == "plain")).scalar_one()
            self.assertEqual(stored.schedule_pattern, "3/3")
            # Меняется только график: ФИО и медцентр остаются прежними.
            self.assertEqual(stored.full_name, "Новый сотрудник")
            self.assertEqual(stored.center_id, self.center_id)
            listed = {user.login: user for user in staff_routes.list_staff(_=self._admin(db), db=db)}
            self.assertEqual(listed["plain"].schedule.pattern, "3/3")

    def test_admin_changes_existing_schedule(self):
        with self.Session() as db:
            self._create(db, login="shifted", schedule=schedule(pattern="2/2", hourly_rate="350"))

            updated = self._update_schedule(
                db, "shifted", schedule(pattern="5/2", shift_start="22:00", shift_end="06:00", hourly_rate=None)
            )

            self.assertEqual(updated.schedule.pattern, "5/2")
            self.assertEqual(updated.schedule.shift_start, time(22, 0))
            self.assertEqual(updated.schedule.shift_end, time(6, 0))
            # Ставку в новом графике не указали, значит прежняя не остается.
            self.assertIsNone(updated.schedule.hourly_rate)
            stored = db.execute(select(User).where(User.login == "shifted")).scalar_one()
            self.assertIsNone(stored.hourly_rate)

    def test_empty_schedule_clears_it(self):
        with self.Session() as db:
            self._create(db, login="shifted", schedule=schedule())

            updated = self._update_schedule(db, "shifted", None)

            self.assertIsNone(updated.schedule)
            stored = db.execute(select(User).where(User.login == "shifted")).scalar_one()
            self.assertIsNone(stored.schedule_pattern)
            self.assertIsNone(stored.schedule_start)
            self.assertIsNone(stored.schedule_end)
            self.assertIsNone(stored.hourly_rate)

    def test_update_must_state_the_schedule(self):
        # Запрос без поля schedule не должен стереть график: поле обязательно, а null — это «снять».
        with self.assertRaises(ValidationError):
            StaffScheduleUpdate.model_validate({})
        self.assertIsNone(StaffScheduleUpdate.model_validate({"schedule": None}).schedule)
        with self.assertRaises(ValidationError):
            StaffScheduleUpdate(schedule=schedule(pattern="1/1"))

    def test_schedule_is_changed_only_for_staff_accounts(self):
        with self.Session() as db:
            guest_role = Role(code="guest", name="Гость")
            db.add(guest_role)
            db.flush()
            db.add(
                User(
                    role_id=guest_role.id,
                    login="guest",
                    password_hash=hash_password("guest123"),
                    full_name="Гость",
                )
            )
            db.commit()
            guest = db.execute(select(User).where(User.login == "guest")).scalar_one()

            for user_id in (guest.id, 999_999):
                with self.subTest(user_id=user_id), self.assertRaises(HTTPException) as raised:
                    staff_routes.update_staff_schedule(
                        user_id=user_id,
                        payload=StaffScheduleUpdate(schedule=schedule()),
                        background_tasks=BackgroundTasks(),
                        admin=self._admin(db),
                        db=db,
                    )
                self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
