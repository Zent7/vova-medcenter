"""График сотрудника по медцентрам: смена, время «со скольки – до скольки» и ставка часа.

У каждого медцентра сотрудника свой график. Он задается при создании учетной записи и меняется
кнопкой «График» у существующего сотрудника (`PUT /staff/{id}/schedules`), где все графики
передаются целиком. Смену можно выбрать только из пяти вариантов, время и ставка проверяются.
Ставка одна на учетную запись. График можно задать только в медцентре, где сотрудник работает.
"""

from datetime import date, time
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from unittest import mock

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
from app.models.staff_center_schedule import StaffCenterSchedule  # noqa: E402
from app.models.staff_schedule_day import StaffScheduleDay  # noqa: E402
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


def schedule(center_id: int, **overrides) -> dict:
    values = {"center_id": center_id, "pattern": "2/2", "shift_start": "08:00", "shift_end": "20:00"}
    values.update(overrides)
    return values


class StaffScheduleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        with self.Session() as db:
            center_a = Center(code="center-a", name="Первый центр")
            center_b = Center(code="center-b", name="Второй центр")
            db.add_all([center_a, center_b])
            roles = {code: Role(code=code, name=code) for code in ("admin", "doctor")}
            db.add_all(roles.values())
            db.flush()
            self.center_a, self.center_b = center_a.id, center_b.id
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

    def _create(self, db, login="new", centers=None, **overrides):
        payload = StaffUserCreate(**staff_payload(login=login, center_ids=centers or [self.center_a], **overrides))
        return staff_routes.create_staff(payload=payload, background_tasks=BackgroundTasks(), current_user=self._admin(db), db=db)

    def _plan_days(self, db, login):
        user = db.execute(select(User).where(User.login == login)).scalar_one()
        return list(
            db.execute(select(StaffScheduleDay).where(StaffScheduleDay.user_id == user.id).order_by(StaffScheduleDay.work_date)).scalars()
        )

    def _schedules_by_center(self, staff) -> dict:
        return {item.center_id: (item.pattern, item.shift_start, item.shift_end) for item in staff.schedules}

    def test_new_schedule_plans_shifts_from_today_to_month_end(self):
        with self.Session() as db, mock.patch("app.services.work_schedule.local_today", return_value=date(2026, 11, 7)):
            self._create(db, schedules=[schedule(self.center_a)])  # 2/2, 08:00-20:00

            stored = db.execute(select(User).where(User.login == "new")).scalar_one()
            self.assertEqual(stored.schedule_in(self.center_a).schedule_anchor_date, date(2026, 11, 7))
            days = self._plan_days(db, "new")
            # 7 и 8 — первая и вторая смена цикла, 9 и 10 — отдых; до конца ноября план идет по кругу.
            self.assertEqual(
                [(day.work_date.day, day.shift_no) for day in days],
                [(7, 1), (8, 2), (11, 1), (12, 2), (15, 1), (16, 2), (19, 1), (20, 2), (23, 1), (24, 2), (27, 1), (28, 2)],
            )
            self.assertTrue(all(day.kind == "shift" and day.source == "pattern" for day in days))
            self.assertTrue(all(day.start_time == time(8) and day.end_time == time(20) for day in days))

    def test_employee_created_without_schedule_gets_no_plan(self):
        with self.Session() as db, mock.patch("app.services.work_schedule.local_today", return_value=date(2026, 11, 7)):
            self._create(db, login="plain")

            stored = db.execute(select(User).where(User.login == "plain")).scalar_one()
            self.assertEqual(stored.center_schedules, [])
            self.assertEqual(self._plan_days(db, "plain"), [])

    def test_saving_a_schedule_without_first_shift_starts_it_today(self):
        # Сотрудник с графиком, у которого первой смены нет (как раньше сохраненные графики).
        with self.Session() as db, mock.patch("app.services.work_schedule.local_today", return_value=date(2026, 11, 7)):
            self._create(db, login="old")
            old = db.execute(select(User).where(User.login == "old")).scalar_one()
            old.center_schedules.append(
                StaffCenterSchedule(center_id=self.center_a, schedule_pattern="2/2", schedule_start=time(8), schedule_end=time(20))
            )
            db.commit()

            self._update_schedules(db, "old", [schedule(self.center_a)])

            stored = db.execute(select(User).where(User.login == "old")).scalar_one()
            self.assertEqual(stored.schedule_in(self.center_a).schedule_anchor_date, date(2026, 11, 7))
            self.assertEqual(len(self._plan_days(db, "old")), 12)

    def test_saving_a_schedule_keeps_the_first_shift_already_set(self):
        with self.Session() as db, mock.patch("app.services.work_schedule.local_today", return_value=date(2026, 11, 7)):
            self._create(db, login="anna", schedules=[schedule(self.center_a)])
            anna = db.execute(select(User).where(User.login == "anna")).scalar_one()
            anna.schedule_in(self.center_a).schedule_anchor_date = date(2026, 11, 3)  # первую смену уже назначили кнопкой
            db.commit()
            plan_before = len(self._plan_days(db, "anna"))

            self._update_schedules(db, "anna", [schedule(self.center_a, shift_end="21:00")])

            stored = db.execute(select(User).where(User.login == "anna")).scalar_one()
            self.assertEqual(stored.schedule_in(self.center_a).schedule_anchor_date, date(2026, 11, 3))
            self.assertEqual(len(self._plan_days(db, "anna")), plan_before)

    def test_schedules_are_saved_per_center_and_returned(self):
        with self.Session() as db:
            created = self._create(
                db,
                centers=[self.center_a, self.center_b],
                schedules=[schedule(self.center_a, hourly_rate=None), schedule(self.center_b, pattern="5/2", shift_start="09:00", shift_end="18:00")],
                hourly_rate="350.50",
            )

            self.assertEqual(
                self._schedules_by_center(created),
                {self.center_a: ("2/2", time(8, 0), time(20, 0)), self.center_b: ("5/2", time(9, 0), time(18, 0))},
            )
            self.assertEqual(created.hourly_rate, Decimal("350.50"))
            self.assertEqual(created.schedules[0].center_name, "Первый центр")
            stored = db.execute(select(User).where(User.login == "new")).scalar_one()
            self.assertEqual(len(stored.center_schedules), 2)

    def test_employee_created_without_schedule_has_none(self):
        with self.Session() as db:
            created = self._create(db)

            self.assertEqual(created.schedules, [])
            self.assertIsNone(created.hourly_rate)

    def test_rate_is_optional(self):
        with self.Session() as db:
            created = self._create(db, schedules=[schedule(self.center_a)], hourly_rate=None)

            self.assertEqual(created.schedules[0].pattern, "2/2")
            self.assertIsNone(created.hourly_rate)

    def test_night_shift_keeps_the_hours_as_entered(self):
        with self.Session() as db:
            created = self._create(db, schedules=[schedule(self.center_a, shift_start="20:00", shift_end="08:00")])

            self.assertEqual((created.schedules[0].shift_start, created.schedules[0].shift_end), (time(20, 0), time(8, 0)))

    def test_schedule_is_listed_for_staff(self):
        with self.Session() as db:
            self._create(db, login="shifted", schedules=[schedule(self.center_a, pattern="5/2")], hourly_rate="350")
            self._create(db, login="plain")
            listed = {user.login: user for user in staff_routes.list_staff(_=self._admin(db), db=db)}

        self.assertEqual(listed["shifted"].schedules[0].pattern, "5/2")
        self.assertEqual(listed["shifted"].hourly_rate, Decimal("350"))
        self.assertEqual(listed["plain"].schedules, [])

    def test_only_the_five_patterns_are_accepted(self):
        for pattern in ("2/2", "3/3", "4/4", "5/2", "6/1"):
            with self.subTest(pattern=pattern):
                created = StaffUserCreate(**staff_payload(schedules=[schedule(1, pattern=pattern)]))
                self.assertEqual(created.schedules[0].pattern, pattern)
        for pattern in ("1/1", "7/7", "2/3", "", "двое через двое"):
            with self.subTest(pattern=pattern), self.assertRaises(ValidationError):
                StaffUserCreate(**staff_payload(schedules=[schedule(1, pattern=pattern)]))

    def test_both_times_are_required_and_must_be_clock_times(self):
        for missing in ("shift_start", "shift_end"):
            values = schedule(1)
            del values[missing]
            with self.subTest(missing=missing), self.assertRaises(ValidationError):
                StaffUserCreate(**staff_payload(schedules=[values]))
        with self.assertRaises(ValidationError):
            StaffUserCreate(**staff_payload(schedules=[schedule(1, shift_end="25:00")]))

    def test_rate_cannot_be_negative_or_finer_than_kopecks(self):
        for rate in ("-1", "350.555"):
            with self.subTest(rate=rate), self.assertRaises(ValidationError):
                StaffUserCreate(**staff_payload(hourly_rate=rate))

    def test_schedule_only_in_a_center_the_employee_works_in(self):
        with self.Session() as db:
            with self.assertRaises(HTTPException) as caught:
                self._create(db, centers=[self.center_a], schedules=[schedule(self.center_b)])
            self.assertEqual(caught.exception.status_code, 400)

    def test_one_schedule_per_center(self):
        with self.Session() as db:
            with self.assertRaises(HTTPException) as caught:
                self._create(db, schedules=[schedule(self.center_a), schedule(self.center_a, pattern="3/3")])
            self.assertEqual(caught.exception.status_code, 400)

    def test_admin_cannot_have_a_schedule(self):
        with self.Session() as db:
            with self.assertRaises(HTTPException) as caught:
                self._create(db, login="boss", role_code="admin", centers=[], schedules=[schedule(self.center_a)])
            self.assertEqual(caught.exception.status_code, 400)

    def _update_schedules(self, db, login, schedules, hourly_rate=None):
        user = db.execute(select(User).where(User.login == login)).scalar_one()
        payload = StaffScheduleUpdate(schedules=schedules, hourly_rate=hourly_rate)
        return staff_routes.update_staff_schedules(user_id=user.id, payload=payload, background_tasks=BackgroundTasks(), admin=self._admin(db), db=db)

    def test_admin_sets_schedules_of_existing_employee(self):
        with self.Session() as db:
            self._create(db, login="plain", centers=[self.center_a, self.center_b])

            updated = self._update_schedules(
                db,
                "plain",
                [schedule(self.center_a, pattern="3/3", shift_start="07:30", shift_end="19:30"), schedule(self.center_b, pattern="4/4")],
                hourly_rate="420",
            )

            self.assertEqual(
                self._schedules_by_center(updated),
                {self.center_a: ("3/3", time(7, 30), time(19, 30)), self.center_b: ("4/4", time(8, 0), time(20, 0))},
            )
            self.assertEqual(updated.hourly_rate, Decimal("420"))
            stored = db.execute(select(User).where(User.login == "plain")).scalar_one()
            # Меняются только графики и ставка: ФИО и медцентр остаются прежними.
            self.assertEqual(stored.full_name, "Новый сотрудник")
            self.assertEqual(stored.center_id, self.center_a)
            listed = {user.login: user for user in staff_routes.list_staff(_=self._admin(db), db=db)}
            self.assertEqual(listed["plain"].schedules[0].pattern, "3/3")

    def test_medcenter_left_out_of_the_update_loses_its_schedule(self):
        with self.Session() as db:
            self._create(db, login="shifted", centers=[self.center_a, self.center_b], schedules=[schedule(self.center_a), schedule(self.center_b)], hourly_rate="350")

            updated = self._update_schedules(db, "shifted", [schedule(self.center_a, pattern="5/2", shift_start="22:00", shift_end="06:00")])

            self.assertEqual(self._schedules_by_center(updated), {self.center_a: ("5/2", time(22, 0), time(6, 0))})
            # Ставку в запросе не передали, значит прежняя не остается.
            self.assertIsNone(updated.hourly_rate)
            stored = db.execute(select(User).where(User.login == "shifted")).scalar_one()
            self.assertIsNone(stored.hourly_rate)

    def test_empty_schedules_clear_them(self):
        with self.Session() as db:
            self._create(db, login="shifted", schedules=[schedule(self.center_a)], hourly_rate="300")

            updated = self._update_schedules(db, "shifted", [])

            self.assertEqual(updated.schedules, [])
            self.assertIsNone(updated.hourly_rate)
            stored = db.execute(select(User).where(User.login == "shifted")).scalar_one()
            self.assertEqual(stored.center_schedules, [])

    def test_update_must_state_the_schedules(self):
        # Запрос без поля schedules не должен стереть графики: поле обязательно, пустой список — это «снять».
        with self.assertRaises(ValidationError):
            StaffScheduleUpdate.model_validate({})
        self.assertEqual(StaffScheduleUpdate.model_validate({"schedules": []}).schedules, [])
        with self.assertRaises(ValidationError):
            StaffScheduleUpdate(schedules=[schedule(1, pattern="1/1")])

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
                    staff_routes.update_staff_schedules(
                        user_id=user_id,
                        payload=StaffScheduleUpdate(schedules=[schedule(self.center_a)]),
                        background_tasks=BackgroundTasks(),
                        admin=self._admin(db),
                        db=db,
                    )
                self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
