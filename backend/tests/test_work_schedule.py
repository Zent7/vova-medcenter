"""График работы по дням: смены по шаблону, отгулы, больничные, отпуска, факт и суммы.

Шаблон задает порядок, первая смена (`schedule_anchor_date`) ставит начало цикла. «Создать
график» продолжает порядок на следующий месяц: если 31 числа у сотрудника 4/4 была вторая
смена, 1 числа будет третья. Ручной график без шаблона остается пустым. Факт по умолчанию
равен плану. Таблица открыта админу, врачу и оператору, ставки и правки — только админу.
"""

from datetime import date, time
from decimal import Decimal
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
from app.api.v1.routes import work_schedule as routes  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.staff_schedule_day import StaffScheduleDay  # noqa: E402
from app.models.user import Role, User  # noqa: E402
from app.schemas.work_schedule import WorkScheduleDayUpdate, WorkScheduleFactItem  # noqa: E402
from app.services import work_schedule as service  # noqa: E402


ROLE_CODES = ("admin", "operator", "doctor", "chairman", "guest")
SHIFT_START = time(8, 0)
SHIFT_END = time(20, 0)


def _dependency_calls(dependant) -> set:
    calls = set()
    for child in dependant.dependencies:
        calls.add(child.call)
        calls |= _dependency_calls(child)
    return calls


def make_user(db, roles, role_code, login, full_name, center=None, pattern=None, rate=None):
    user = User(
        role_id=roles[role_code].id,
        login=login,
        password_hash=hash_password(f"{login}123"),
        full_name=full_name,
        is_active=True,
        center_id=center.id if center is not None else None,
        schedule_pattern=pattern,
        schedule_start=SHIFT_START if pattern else None,
        schedule_end=SHIFT_END if pattern else None,
        hourly_rate=Decimal(rate) if rate else None,
    )
    db.add(user)
    db.flush()
    return user


class WorkScheduleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        with self.Session() as db:
            center_a = Center(code="center-a", name="Мед-Авто")
            center_b = Center(code="center-b", name="Медилэнд")
            db.add_all([center_a, center_b])
            roles = {code: Role(code=code, name=code) for code in ROLE_CODES}
            db.add_all(roles.values())
            db.flush()
            make_user(db, roles, "admin", "admin", "Админ")
            make_user(db, roles, "guest", "guest", "Гость", center=center_a)
            make_user(db, roles, "operator", "anna", "Анна", center=center_a, pattern="4/4", rate="300")
            make_user(db, roles, "doctor", "boris", "Борис", center=center_a, pattern="2/2")
            make_user(db, roles, "doctor", "viktor", "Виктор", center=center_b)
            make_user(db, roles, "chairman", "chair", "Председатель", center=center_a)
            db.commit()

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _user(self, db, login: str) -> User:
        return db.execute(select(User).where(User.login == login)).scalar_one()

    def _set_anchor(self, db, login: str, anchor: date):
        self._user(db, login).schedule_anchor_date = anchor
        db.commit()

    def _grid_row(self, db, login: str, year: int, month: int, viewer_login: str = "admin"):
        grid = routes.read_month(year=year, month=month, viewer=self._user(db, viewer_login), db=db)
        full_name = self._user(db, login).full_name
        return next(item for item in grid.rows if item.full_name == full_name)

    def _row_days(self, db, login: str, year: int, month: int) -> dict:
        """Записи графика сотрудника за месяц: {день: (вид, номер смены)}."""
        return {day.work_date.day: (day.kind, day.shift_no) for day in self._grid_row(db, login, year, month).days}


class ShiftRulesTests(WorkScheduleTests):
    def test_night_shift_counts_through_midnight(self):
        self.assertEqual(service.shift_minutes(time(8), time(20)), 720)
        self.assertEqual(service.shift_minutes(time(20), time(8)), 720)
        self.assertEqual(service.shift_minutes(time(8, 30), time(12)), 210)

    def test_pattern_shifts_are_numbered_from_the_first_shift(self):
        with self.Session() as db:
            user = self._user(db, "anna")
            user.schedule_anchor_date = date(2026, 10, 30)
            self.assertEqual(
                service.pattern_shifts(user, date(2026, 10, 29), date(2026, 11, 7)),
                [(date(2026, 10, 30), 1), (date(2026, 10, 31), 2), (date(2026, 11, 1), 3), (date(2026, 11, 2), 4), (date(2026, 11, 7), 1)],
            )

    def test_no_pattern_shifts_without_a_pattern_or_first_shift(self):
        with self.Session() as db:
            self.assertEqual(service.pattern_shifts(self._user(db, "anna"), date(2026, 11, 1), date(2026, 11, 30)), [])
            self.assertEqual(service.pattern_shifts(self._user(db, "viktor"), date(2026, 11, 1), date(2026, 11, 30)), [])

    def test_day_update_needs_times_for_a_shift_and_none_for_leave(self):
        with self.assertRaises(HTTPException):
            service.check_day_update("shift", None, SHIFT_END)
        with self.assertRaises(HTTPException):
            service.check_day_update("shift", SHIFT_START, SHIFT_START)
        with self.assertRaises(HTTPException):
            service.check_day_update("dayoff", SHIFT_START, SHIFT_END)
        service.check_day_update("shift", SHIFT_END, SHIFT_START)  # ночная смена
        service.check_day_update("vacation", None, None)

    def test_absence_period_must_be_ordered_and_short(self):
        with self.assertRaises(HTTPException):
            service.check_absence_period(date(2026, 11, 5), date(2026, 11, 1))
        with self.assertRaises(HTTPException):
            service.check_absence_period(date(2026, 1, 1), date(2027, 6, 1))
        self.assertEqual(len(service.check_absence_period(date(2026, 11, 1), date(2026, 11, 3))), 3)


class MonthGenerationTests(WorkScheduleTests):
    def test_generate_continues_the_sequence_into_the_next_month(self):
        with self.Session() as db:
            self._set_anchor(db, "anna", date(2026, 10, 30))
            self.assertEqual(service.generate_month(db, 2026, 10)["created"], 2)  # 30 и 31 октября
            result = service.generate_month(db, 2026, 11)
            # Борис с шаблоном, но без первой смены, в список «не назначено» попадает.
            self.assertEqual(result["users_without_start"], ["Борис"])

            days = self._row_days(db, "anna", 2026, 11)
            # 31 октября была вторая смена, поэтому 1 ноября — третья, 2 ноября — четвертая.
            self.assertEqual(days[1], ("shift", 3))
            self.assertEqual(days[2], ("shift", 4))
            self.assertNotIn(3, days)
            self.assertEqual(days[7], ("shift", 1))
            self.assertEqual(days[10], ("shift", 4))
            self.assertEqual(sorted(days), [1, 2, 7, 8, 9, 10, 15, 16, 17, 18, 23, 24, 25, 26])

    def test_generate_twice_changes_nothing(self):
        with self.Session() as db:
            self._set_anchor(db, "anna", date(2026, 10, 30))
            service.generate_month(db, 2026, 11)
            self.assertEqual(service.generate_month(db, 2026, 11)["created"], 0)

    def test_manual_employee_without_pattern_stays_empty(self):
        with self.Session() as db:
            result = service.generate_month(db, 2026, 11)
            self.assertNotIn("Виктор", result["users_without_start"])
            self.assertEqual(self._row_days(db, "viktor", 2026, 11), {})

    def test_pattern_without_first_shift_is_reported(self):
        with self.Session() as db:
            result = service.generate_month(db, 2026, 11)
            self.assertEqual(result["created"], 0)
            self.assertEqual(sorted(result["users_without_start"]), ["Анна", "Борис"])

    def test_first_shift_restarts_cycle_and_keeps_leave_and_history(self):
        with self.Session() as db:
            self._set_anchor(db, "anna", date(2026, 10, 30))
            service.generate_month(db, 2026, 10)
            service.generate_month(db, 2026, 11)
            anna = self._user(db, "anna")
            service.put_absence(db, anna, service.days_in_range(date(2026, 11, 8), date(2026, 11, 9)), "vacation")
            db.commit()

            created = service.restart_pattern(db, anna, date(2026, 11, 12))
            db.commit()

            # 12–15, 20–23 и 28–30 ноября: одиннадцать смен от нового начала.
            self.assertEqual(created, 11)
            days = self._row_days(db, "anna", 2026, 11)
            self.assertEqual(days[8], ("vacation", None))
            self.assertEqual(days[9], ("vacation", None))
            self.assertEqual(days[12], ("shift", 1))
            self.assertEqual(days[15], ("shift", 4))
            self.assertNotIn(16, days)
            self.assertNotIn(18, days)
            self.assertEqual(days[20], ("shift", 1))
            self.assertEqual(days[30], ("shift", 3))
            # Смены до нового начала остаются со своими номерами.
            self.assertEqual(days[1], ("shift", 3))
            self.assertEqual(days[2], ("shift", 4))
            october = next(row for row in service.stats_payload(db, 2026, 10)["rows"] if row["full_name"] == "Анна")
            self.assertEqual(october["plan"]["days"], 2)

    def test_first_shift_needs_a_pattern(self):
        with self.Session() as db:
            with self.assertRaises(HTTPException) as caught:
                service.restart_pattern(db, self._user(db, "viktor"), date(2026, 11, 3))
            self.assertEqual(caught.exception.status_code, 409)


class DayEditingTests(WorkScheduleTests):
    def test_absence_replaces_shift_and_keeps_the_cycle(self):
        with self.Session() as db:
            self._set_anchor(db, "anna", date(2026, 10, 30))
            service.generate_month(db, 2026, 11)
            anna = self._user(db, "anna")
            service.put_absence(db, anna, service.days_in_range(date(2026, 11, 1), date(2026, 11, 3)), "sick")
            db.commit()

            days = self._row_days(db, "anna", 2026, 11)
            self.assertEqual(days[1], ("sick", None))
            self.assertEqual(days[3], ("sick", None))
            self.assertEqual(days[7], ("shift", 1))

    def test_manual_shift_and_clear(self):
        with self.Session() as db:
            viktor = self._user(db, "viktor")
            service.put_day(db, viktor, date(2026, 11, 4), "shift", time(9), time(18))
            db.commit()
            self.assertEqual(self._row_days(db, "viktor", 2026, 11), {4: ("shift", None)})
            self.assertEqual(service.clear_day(db, viktor, date(2026, 11, 4)), 1)
            db.commit()
            self.assertEqual(self._row_days(db, "viktor", 2026, 11), {})
            self.assertEqual(service.clear_day(db, viktor, date(2026, 11, 4)), 0)

    def test_leave_day_drops_times_and_facts(self):
        with self.Session() as db:
            viktor = self._user(db, "viktor")
            service.put_day(db, viktor, date(2026, 11, 4), "shift", time(9), time(18))
            service.put_facts(db, viktor, [{"work_date": date(2026, 11, 4), "start_time": time(9, 30), "end_time": time(18)}])
            service.put_day(db, viktor, date(2026, 11, 4), "dayoff", None, None)
            db.commit()
            row = db.execute(select(StaffScheduleDay).where(StaffScheduleDay.user_id == viktor.id)).scalar_one()
            self.assertEqual(row.kind, "dayoff")
            self.assertIsNone(row.start_time)
            self.assertIsNone(row.fact_start_time)
            self.assertEqual(row.source, "manual")

    def test_facts_only_on_shift_days_and_all_or_nothing(self):
        with self.Session() as db:
            viktor = self._user(db, "viktor")
            service.put_day(db, viktor, date(2026, 11, 4), "vacation", None, None)
            db.commit()
            with self.assertRaises(HTTPException) as caught:
                service.put_facts(db, viktor, [{"work_date": date(2026, 11, 4), "start_time": time(9), "end_time": time(18)}])
            self.assertEqual(caught.exception.status_code, 409)
            with self.assertRaises(HTTPException) as caught:
                service.put_facts(db, viktor, [{"work_date": date(2026, 11, 4), "start_time": time(9), "end_time": None}])
            self.assertEqual(caught.exception.status_code, 400)

    def test_fact_items_parse_times_and_allow_clearing(self):
        item = WorkScheduleFactItem(work_date=date(2026, 11, 4), start_time="09:30", end_time="18:00")
        self.assertEqual(item.start_time, time(9, 30))
        self.assertIsNone(WorkScheduleFactItem(work_date=date(2026, 11, 4)).start_time)
        self.assertEqual(WorkScheduleDayUpdate(kind="dayoff").kind, "dayoff")


class StatsTests(WorkScheduleTests):
    def test_plan_and_fact_hours_are_multiplied_by_the_rate(self):
        with self.Session() as db:
            self._set_anchor(db, "anna", date(2026, 10, 30))
            service.generate_month(db, 2026, 11)
            service.put_facts(db, self._user(db, "anna"), [{"work_date": date(2026, 11, 1), "start_time": time(8), "end_time": time(21)}])
            db.commit()

            row = next(item for item in service.stats_payload(db, 2026, 11)["rows"] if item["full_name"] == "Анна")
            # 14 смен по 12 часов; 1 ноября факт 13 часов вместо 12.
            self.assertEqual(row["plan"], {"days": 14, "hours": 168.0, "amount": 50400.0})
            self.assertEqual(row["fact"], {"days": 14, "hours": 169.0, "amount": 50700.0})
            self.assertEqual(row["hourly_rate"], 300.0)

    def test_fact_equals_plan_until_entered_and_leave_counts_zero(self):
        with self.Session() as db:
            self._set_anchor(db, "anna", date(2026, 10, 30))
            service.generate_month(db, 2026, 11)
            service.put_absence(db, self._user(db, "anna"), service.days_in_range(date(2026, 11, 1), date(2026, 11, 2)), "vacation")
            db.commit()
            row = next(item for item in service.stats_payload(db, 2026, 11)["rows"] if item["full_name"] == "Анна")
            self.assertEqual(row["plan"]["days"], 12)
            self.assertEqual(row["fact"], row["plan"])
            day_one = next(day for day in row["days"] if day["work_date"] == date(2026, 11, 1))
            self.assertEqual((day_one["plan_hours"], day_one["fact_hours"]), (0.0, 0.0))

    def test_amounts_are_empty_when_rate_is_not_set(self):
        with self.Session() as db:
            self._set_anchor(db, "boris", date(2026, 11, 1))
            service.generate_month(db, 2026, 11)
            row = next(item for item in service.stats_payload(db, 2026, 11)["rows"] if item["full_name"] == "Борис")
            self.assertIsNone(row["hourly_rate"])
            self.assertIsNone(row["plan"]["amount"])
            self.assertGreater(row["plan"]["hours"], 0)

    def test_overnight_shift_counts_twelve_hours(self):
        with self.Session() as db:
            service.put_day(db, self._user(db, "viktor"), date(2026, 11, 5), "shift", time(20), time(8))
            db.commit()
            row = next(item for item in service.stats_payload(db, 2026, 11)["rows"] if item["full_name"] == "Виктор")
            self.assertEqual((row["plan"]["days"], row["plan"]["hours"]), (1, 12.0))


class AccessTests(WorkScheduleTests):
    def test_grid_lists_operators_then_doctors_and_skips_empty_admin(self):
        with self.Session() as db:
            grid = routes.read_month(year=2026, month=11, viewer=self._user(db, "admin"), db=db)
            self.assertEqual([row.full_name for row in grid.rows], ["Анна", "Борис", "Виктор", "Председатель"])
            self.assertTrue(grid.can_edit)
            anna = grid.rows[0]
            self.assertEqual((anna.center.name, anna.center.color), ("Мед-Авто", service.CENTER_PALETTE[0]))

    def test_doctor_and_operator_see_only_own_centers_without_rates(self):
        with self.Session() as db:
            grid = routes.read_month(year=2026, month=11, viewer=self._user(db, "anna"), db=db)
            self.assertEqual([row.full_name for row in grid.rows], ["Анна", "Борис", "Председатель"])
            self.assertFalse(grid.can_edit)
            self.assertNotIn("hourly_rate", grid.model_dump_json())

    def test_viewers_are_admin_operator_and_doctor_only(self):
        with self.Session() as db:
            self.assertEqual(routes.require_schedule_viewer(current_user=self._user(db, "anna")).login, "anna")
            with self.assertRaises(HTTPException) as caught:
                routes.require_schedule_viewer(current_user=self._user(db, "chair"))
            self.assertEqual(caught.exception.status_code, 403)
            with self.assertRaises(HTTPException):
                routes.require_schedule_viewer(current_user=self._user(db, "guest"))

    def test_only_the_month_table_is_open_to_viewers(self):
        for route in (item for item in routes.router.routes if isinstance(item, APIRoute)):
            calls = _dependency_calls(route.dependant)
            if route.path == "/month":
                self.assertIn(routes.require_schedule_viewer, calls)
                self.assertNotIn(auth_routes.require_admin, calls)
            else:
                self.assertIn(auth_routes.require_admin, calls, f"{sorted(route.methods)} {route.path} открыт не только админу")

    def test_guest_is_not_a_schedule_employee(self):
        with self.Session() as db:
            with self.assertRaises(HTTPException) as caught:
                service.load_schedule_user(db, self._user(db, "guest").id)
            self.assertEqual(caught.exception.status_code, 404)
            with self.assertRaises(HTTPException):
                service.load_schedule_user(db, 999999)


class MigrationTests(unittest.TestCase):
    def test_model_and_migration_agree_on_the_new_schema(self):
        table = Base.metadata.tables["staff_schedule_days"]
        self.assertIn("shift_no", table.columns)
        self.assertIn("schedule_anchor_date", Base.metadata.tables["users"].columns)
        migration = (Path(__file__).resolve().parents[1] / "migrations/versions/20261106_0028_add_staff_schedule_days.py").read_text(encoding="utf-8")
        self.assertIn('down_revision: str | None = "20261106_0027"', migration)
        self.assertIn('"shift_no"', migration)


if __name__ == "__main__":
    unittest.main()
