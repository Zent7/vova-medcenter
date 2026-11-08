"""График работы по медцентрам: смены по шаблону, отгулы, больничные, отпуска, факт и суммы.

У каждого медцентра свой график сотрудника: шаблон, время смены и первая смена цикла. Сотрудник с
двумя медцентрами появляется в таблице каждого из них. Если в один день он стоит сменой в двух
медцентрах, оба дня помечаются как пересечение. Таблица открыта админу, врачу и оператору; ставки,
суммы и правки — только админу. Врач и оператор видят в статистике только свои часы своего медцентра.
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest

from fastapi import BackgroundTasks, HTTPException
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
from app.models.staff_center_schedule import StaffCenterSchedule  # noqa: E402
from app.models.user import Role, User  # noqa: E402
from app.models.work_time_entry import WorkTimeEntry  # noqa: E402
from app.schemas.work_schedule import WorkScheduleFactItem, WorkScheduleFirstShift  # noqa: E402
from app.services import work_schedule as service  # noqa: E402
from app.services import work_status  # noqa: E402


ROLE_CODES = ("admin", "operator", "doctor", "chairman", "guest")
SHIFT_START = time(8, 0)
SHIFT_END = time(20, 0)


def _dependency_calls(dependant) -> set:
    calls = set()
    for child in dependant.dependencies:
        calls.add(child.call)
        calls |= _dependency_calls(child)
    return calls


def add_schedule(user, center, pattern, anchor=None, start=SHIFT_START, end=SHIFT_END):
    """График сотрудника в медцентре: шаблон, время смены и первая смена цикла."""
    user.center_schedules.append(
        StaffCenterSchedule(
            center_id=center.id,
            schedule_pattern=pattern,
            schedule_start=start,
            schedule_end=end,
            schedule_anchor_date=anchor,
        )
    )


def make_user(db, roles, role_code, login, full_name, center=None, extra=(), rate=None):
    user = User(
        role_id=roles[role_code].id,
        login=login,
        password_hash=hash_password(f"{login}123"),
        full_name=full_name,
        is_active=True,
        center_id=center.id if center is not None else None,
        hourly_rate=Decimal(rate) if rate else None,
    )
    user.extra_centers = list(extra)
    db.add(user)
    db.flush()
    return user


MSK = timezone(timedelta(hours=3))  # Москва без летнего времени с 2014 года


def msk(day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=MSK)


def utc(day: int, hour: int = 0, minute: int = 0) -> datetime:
    """Отметка так, как ее пишут в таблицу: в UTC."""
    return msk(day, hour, minute).astimezone(timezone.utc)


def stats(db, center: Center, year: int, month: int, now: datetime = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)) -> dict:
    """Статистика админа так, как ее отдает маршрут: факт берется из отметок за месяц."""
    first, last = service.month_bounds(year, month)
    return service.stats_payload(db, center, year, month, work_status.fact_minutes_by_user(db, first, last, now))


class WorkScheduleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        with self.Session() as db:
            center_a = Center(code="center-a", name="Мед-Авто")
            center_b = Center(code="center-b", name="Медилэнд")
            center_c = Center(code="center-c", name="Здравница")
            db.add_all([center_a, center_b, center_c])
            roles = {code: Role(code=code, name=code) for code in ROLE_CODES}
            db.add_all(roles.values())
            db.flush()
            make_user(db, roles, "admin", "admin", "Админ")
            make_user(db, roles, "guest", "guest", "Гость", center=center_a)
            anna = make_user(db, roles, "operator", "anna", "Анна", center=center_a, rate="300")
            add_schedule(anna, center_a, "4/4", anchor=date(2026, 11, 1))
            boris = make_user(db, roles, "doctor", "boris", "Борис", center=center_a)
            add_schedule(boris, center_a, "2/2", anchor=date(2026, 11, 1))
            make_user(db, roles, "doctor", "viktor", "Виктор", center=center_b)
            make_user(db, roles, "chairman", "chair", "Председатель", center=center_a)
            make_user(db, roles, "operator", "olga", "Ольга", center=center_a)
            db.commit()

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _user(self, db, login: str) -> User:
        return db.execute(select(User).where(User.login == login)).scalar_one()

    def _center(self, db, code: str) -> Center:
        return db.execute(select(Center).where(Center.code == code)).scalar_one()

    def _schedule(self, db, login: str, code: str) -> StaffCenterSchedule:
        user = self._user(db, login)
        return next(item for item in user.center_schedules if item.center.code == code)

    def _grid(self, db, viewer_login: str, code: str | None, year: int = 2026, month: int = 11):
        center_id = self._center(db, code).id if code else None
        return routes.read_month(year=year, month=month, center_id=center_id, viewer=self._user(db, viewer_login), db=db)

    def _grid_row(self, db, login: str, code: str, viewer_login: str = "admin"):
        grid = self._grid(db, viewer_login, code)
        full_name = self._user(db, login).full_name
        return next(item for item in grid.rows if item.full_name == full_name)

    def _row_days(self, db, login: str, code: str) -> dict:
        """Записи графика сотрудника в медцентре за ноябрь: {день: (вид, номер смены)}."""
        return {day.work_date.day: (day.kind, day.shift_no) for day in self._grid_row(db, login, code).days}


class ShiftRulesTests(WorkScheduleTests):
    def test_night_shift_counts_through_midnight(self):
        self.assertEqual(service.shift_minutes(time(8), time(20)), 720)
        self.assertEqual(service.shift_minutes(time(20), time(8)), 720)

    def test_pattern_shifts_are_numbered_from_the_first_shift(self):
        with self.Session() as db:
            schedule = self._schedule(db, "anna", "center-a")
            self.assertEqual(
                service.pattern_shifts(schedule, date(2026, 11, 1), date(2026, 11, 8)),
                [(date(2026, 11, 1), 1), (date(2026, 11, 2), 2), (date(2026, 11, 3), 3), (date(2026, 11, 4), 4)],
            )

    def test_no_pattern_shifts_without_a_first_shift(self):
        with self.Session() as db:
            viktor = self._user(db, "viktor")
            center_b = self._center(db, "center-b")
            add_schedule(viktor, center_b, "2/2", anchor=None)
            db.flush()
            schedule = viktor.schedule_in(center_b.id)
            self.assertEqual(service.pattern_shifts(schedule, date(2026, 11, 1), date(2026, 11, 30)), [])

    def test_day_update_needs_times_for_a_shift_and_none_for_leave(self):
        service.check_day_update("shift", SHIFT_START, SHIFT_END)
        for kind, start, end in (("shift", None, SHIFT_END), ("shift", SHIFT_START, SHIFT_START), ("dayoff", SHIFT_START, None)):
            with self.assertRaises(HTTPException) as caught:
                service.check_day_update(kind, start, end)
            self.assertEqual(caught.exception.status_code, 400)

    def test_absence_period_must_be_ordered_and_short(self):
        self.assertEqual(len(service.check_absence_period(date(2026, 11, 1), date(2026, 11, 3))), 3)
        with self.assertRaises(HTTPException):
            service.check_absence_period(date(2026, 11, 3), date(2026, 11, 1))
        with self.assertRaises(HTTPException):
            service.check_absence_period(date(2026, 1, 1), date(2027, 6, 1))


class MonthGenerationTests(WorkScheduleTests):
    def test_generate_continues_the_sequence_into_the_next_month(self):
        with self.Session() as db:
            self._schedule(db, "anna", "center-a").schedule_anchor_date = date(2026, 10, 31)
            db.commit()
            center = self._center(db, "center-a")
            self.assertEqual(service.generate_month(db, center, 2026, 10)["created"], 1)
            service.generate_month(db, center, 2026, 11)
            days = self._row_days(db, "anna", "center-a")
            # Октябрьская смена 31-го — первая цикла; 1–3 ноября продолжают нумерацию, 4 ноября — отдых.
            self.assertEqual(days[1], ("shift", 2))
            self.assertEqual(days[3], ("shift", 4))
            self.assertNotIn(4, days)

    def test_generate_twice_changes_nothing(self):
        with self.Session() as db:
            center = self._center(db, "center-a")
            self.assertGreater(service.generate_month(db, center, 2026, 11)["created"], 0)
            self.assertEqual(service.generate_month(db, center, 2026, 11)["created"], 0)

    def test_manual_employee_without_schedule_stays_empty(self):
        with self.Session() as db:
            service.generate_month(db, self._center(db, "center-b"), 2026, 11)
            self.assertEqual(self._row_days(db, "viktor", "center-b"), {})

    def test_pattern_without_first_shift_is_reported(self):
        with self.Session() as db:
            self._schedule(db, "anna", "center-a").schedule_anchor_date = None
            db.commit()
            result = service.generate_month(db, self._center(db, "center-a"), 2026, 11)
            self.assertIn("Анна", result["users_without_start"])
            self.assertEqual(self._row_days(db, "anna", "center-a"), {})

    def test_first_shift_restarts_cycle_and_keeps_leave_and_history(self):
        with self.Session() as db:
            anna = self._user(db, "anna")
            center = self._center(db, "center-a")
            service.generate_month(db, center, 2026, 11)
            service.put_absence(db, anna, center.id, [date(2026, 11, 5)], "vacation")
            db.commit()
            created = service.restart_pattern(db, anna, self._schedule(db, "anna", "center-a"), date(2026, 11, 3))
            db.commit()
            self.assertGreater(created, 0)
            days = self._row_days(db, "anna", "center-a")
            # Цикл 4/4 начат 3 ноября: 3–6 смены 1–4, 7–10 отдых, 11 снова смена 1; отпуск 5-го сохранен.
            self.assertEqual(days[2], ("shift", 2))
            self.assertEqual(days[3], ("shift", 1))
            self.assertEqual(days[4], ("shift", 2))
            self.assertEqual(days[5], ("vacation", None))
            self.assertEqual(days[6], ("shift", 4))
            self.assertNotIn(7, days)
            self.assertEqual(days[11], ("shift", 1))

    def test_first_shift_needs_a_schedule_in_this_center(self):
        with self.Session() as db:
            with self.assertRaises(HTTPException) as caught:
                routes.start_first_shift(
                    user_id=self._user(db, "viktor").id,
                    payload=WorkScheduleFirstShift(work_date=date(2026, 11, 3)),
                    background_tasks=BackgroundTasks(),
                    center_id=self._center(db, "center-b").id,
                    admin=self._user(db, "admin"),
                    db=db,
                )
            self.assertEqual(caught.exception.status_code, 409)


class DayEditingTests(WorkScheduleTests):
    def test_absence_replaces_shift_and_keeps_the_cycle(self):
        with self.Session() as db:
            center = self._center(db, "center-a")
            service.generate_month(db, center, 2026, 11)
            service.put_absence(db, self._user(db, "anna"), center.id, [date(2026, 11, 1), date(2026, 11, 2)], "sick")
            db.commit()
            days = self._row_days(db, "anna", "center-a")
            self.assertEqual(days[1], ("sick", None))
            self.assertEqual(days[2], ("sick", None))
            self.assertEqual(days[3], ("shift", 3))
            self.assertEqual(days[4], ("shift", 4))

    def test_manual_shift_and_clear(self):
        with self.Session() as db:
            anna = self._user(db, "anna")
            center = self._center(db, "center-a")
            service.put_day(db, anna, center.id, date(2026, 11, 15), "shift", time(10), time(18))
            db.commit()
            self.assertEqual(service.day_state(db, anna, center.id, date(2026, 11, 15))["start"], "10:00")
            self.assertEqual(service.clear_day(db, anna, center.id, date(2026, 11, 15)), 1)
            self.assertIsNone(service.day_state(db, anna, center.id, date(2026, 11, 15)))

    def test_leave_day_drops_times_and_facts(self):
        with self.Session() as db:
            anna = self._user(db, "anna")
            center = self._center(db, "center-a")
            service.put_day(db, anna, center.id, date(2026, 11, 15), "dayoff", None, None)
            db.commit()
            state = service.day_state(db, anna, center.id, date(2026, 11, 15))
            self.assertEqual((state["kind"], state["start"], state["end"]), ("dayoff", None, None))

    def test_facts_only_on_shift_days_and_all_or_nothing(self):
        with self.Session() as db:
            anna = self._user(db, "anna")
            center = self._center(db, "center-a")
            service.generate_month(db, center, 2026, 11)
            db.commit()
            service.put_facts(db, anna, center.id, [{"work_date": date(2026, 11, 1), "start_time": time(9), "end_time": time(18)}])
            db.commit()
            self.assertEqual(service.facts_state(db, anna, center.id, [date(2026, 11, 1)]), {date(2026, 11, 1): "09:00-18:00"})
            with self.assertRaises(HTTPException) as on_rest:
                service.put_facts(db, anna, center.id, [{"work_date": date(2026, 11, 5), "start_time": time(9), "end_time": time(18)}])
            self.assertEqual(on_rest.exception.status_code, 409)
            with self.assertRaises(HTTPException) as half:
                service.put_facts(db, anna, center.id, [{"work_date": date(2026, 11, 1), "start_time": time(9), "end_time": None}])
            self.assertEqual(half.exception.status_code, 400)

    def test_fact_items_parse_times_and_allow_clearing(self):
        item = WorkScheduleFactItem(work_date=date(2026, 11, 1), start_time="09:30", end_time="18:00")
        self.assertEqual((item.start_time, item.end_time), (time(9, 30), time(18)))
        cleared = WorkScheduleFactItem(work_date=date(2026, 11, 1))
        self.assertIsNone(cleared.start_time)


class StatsTests(WorkScheduleTests):
    def _row(self, db, center_code: str, full_name: str):
        center = self._center(db, center_code)
        return next(item for item in stats(db, center, 2026, 11)["rows"] if item["full_name"] == full_name)

    def test_plan_and_fact_hours_are_multiplied_by_the_rate(self):
        with self.Session() as db:
            service.generate_month(db, self._center(db, "center-a"), 2026, 11)
            db.commit()
            row = self._row(db, "center-a", "Анна")
            self.assertEqual((row["plan"]["days"], row["plan"]["hours"]), (16, 192.0))
            self.assertEqual(row["plan"]["amount"], 57600.0)
            self.assertEqual(row["center_name"], "Мед-Авто")

    def test_fact_is_only_the_manual_fact_when_there_are_no_marks(self):
        with self.Session() as db:
            anna = self._user(db, "anna")
            center = self._center(db, "center-a")
            service.generate_month(db, center, 2026, 11)
            service.put_facts(db, anna, center.id, [{"work_date": date(2026, 11, 1), "start_time": time(9), "end_time": time(18)}])
            service.put_absence(db, anna, center.id, [date(2026, 11, 9)], "vacation")
            db.commit()
            row = self._row(db, "center-a", "Анна")
            self.assertEqual((row["plan"]["days"], row["plan"]["hours"]), (15, 180.0))
            # Отметок «На работу» нет: факт только ручная правка 1 ноября (9 часов), остальные смены без факта.
            self.assertEqual((row["fact"]["days"], row["fact"]["hours"]), (1, 9.0))

    def _anchor(self, db, login: str, anchor: date) -> None:
        """Первая смена цикла у сотрудника в Мед-Авто: от нее идут смены ноября (у Анны 4/4)."""
        self._schedule(db, login, "center-a").schedule_anchor_date = anchor
        db.commit()

    def test_no_time_marks_means_no_fact_and_leave_counts_zero(self):
        with self.Session() as db:
            self._anchor(db, "anna", date(2026, 10, 30))
            center = self._center(db, "center-a")
            service.generate_month(db, center, 2026, 11)
            service.put_absence(db, self._user(db, "anna"), center.id, service.days_in_range(date(2026, 11, 1), date(2026, 11, 2)), "vacation")
            db.commit()
            row = self._row(db, "center-a", "Анна")
            # Отметок «На работу» нет: план есть, факт нулевой, красных столбцов не будет.
            self.assertEqual(row["plan"]["days"], 12)
            self.assertEqual(row["fact"], {"days": 0, "hours": 0.0, "amount": 0.0})
            day_one = next(day for day in row["days"] if day["work_date"] == date(2026, 11, 1))
            self.assertEqual((day_one["plan_hours"], day_one["fact_hours"]), (0.0, 0.0))
            day_seven = next(day for day in row["days"] if day["work_date"] == date(2026, 11, 7))
            self.assertEqual((day_seven["plan_hours"], day_seven["fact_hours"]), (12.0, 0.0))

    def test_fact_is_the_time_on_the_counter_not_the_schedule(self):
        with self.Session() as db:
            self._anchor(db, "anna", date(2026, 10, 30))
            service.generate_month(db, self._center(db, "center-a"), 2026, 11)
            anna_id = self._user(db, "anna").id
            db.add_all(
                [
                    WorkTimeEntry(user_id=anna_id, started_at=utc(1, 9), ended_at=utc(1, 13)),  # смена 1 ноября: 4 из 12 ч
                    WorkTimeEntry(user_id=anna_id, started_at=utc(3, 10), ended_at=utc(3, 11, 30)),  # выходной: 1,5 ч
                    WorkTimeEntry(user_id=anna_id, started_at=utc(7, 22), ended_at=utc(8, 2)),  # через полночь: по 2 ч
                ]
            )
            db.commit()

            row = self._row(db, "center-a", "Анна")
            days = {day["work_date"]: day for day in row["days"]}
            self.assertEqual(row["plan"], {"days": 14, "hours": 168.0, "amount": 50400.0})
            self.assertEqual(row["fact"], {"days": 4, "hours": 9.5, "amount": 2850.0})
            self.assertEqual((days[date(2026, 11, 1)]["plan_hours"], days[date(2026, 11, 1)]["fact_hours"]), (12.0, 4.0))
            self.assertEqual((days[date(2026, 11, 3)]["plan_hours"], days[date(2026, 11, 3)]["fact_hours"]), (0.0, 1.5))
            self.assertEqual((days[date(2026, 11, 7)]["fact_hours"], days[date(2026, 11, 8)]["fact_hours"]), (2.0, 2.0))

    def test_manual_fact_on_a_shift_replaces_the_marks_of_that_day(self):
        with self.Session() as db:
            self._anchor(db, "anna", date(2026, 10, 30))
            center = self._center(db, "center-a")
            service.generate_month(db, center, 2026, 11)
            anna = self._user(db, "anna")
            db.add(WorkTimeEntry(user_id=anna.id, started_at=utc(1, 9), ended_at=utc(1, 13)))
            service.put_facts(
                db,
                anna,
                center.id,
                [
                    {"work_date": date(2026, 11, 1), "start_time": time(9), "end_time": time(10)},
                    {"work_date": date(2026, 11, 2), "start_time": time(8), "end_time": time(21)},
                ],
            )
            db.commit()

            row = self._row(db, "center-a", "Анна")
            days = {day["work_date"]: day for day in row["days"]}
            # 1 ноября правка 1 ч вместо отметки в 4 ч; 2 ноября отметок нет, а правка есть.
            self.assertEqual((days[date(2026, 11, 1)]["fact_hours"], days[date(2026, 11, 2)]["fact_hours"]), (1.0, 13.0))
            self.assertEqual(row["fact"]["hours"], 14.0)

            # Пустое время снимает правку: 1 ноября снова считается по отметке.
            service.put_facts(db, anna, center.id, [{"work_date": date(2026, 11, 1), "start_time": None, "end_time": None}])
            db.commit()
            row = self._row(db, "center-a", "Анна")
            self.assertEqual(row["fact"]["hours"], 17.0)

    def test_stats_route_counts_the_marks_too(self):
        with self.Session() as db:
            self._anchor(db, "anna", date(2026, 10, 30))
            center = self._center(db, "center-a")
            service.generate_month(db, center, 2026, 11)
            db.add(WorkTimeEntry(user_id=self._user(db, "anna").id, started_at=utc(1, 9), ended_at=utc(1, 13)))
            db.commit()

            routed = routes.read_stats(year=2026, month=11, center_id=center.id, viewer=self._user(db, "admin"), db=db)

            row = next(item for item in routed.rows if item.full_name == "Анна")
            self.assertEqual((row.fact.days, row.fact.hours, row.fact.amount), (1, 4.0, 1200.0))

    def test_marks_within_fifteen_minutes_of_the_shift_edges_count_in_stats(self):
        with self.Session() as db:
            self._anchor(db, "anna", date(2026, 10, 30))
            center = self._center(db, "center-a")
            service.generate_month(db, center, 2026, 11)
            anna_id = self._user(db, "anna").id
            db.add_all(
                [
                    WorkTimeEntry(user_id=anna_id, started_at=utc(1, 8, 10), ended_at=utc(1, 19, 50)),  # опоздание и ранний уход по 10 минут
                    WorkTimeEntry(user_id=anna_id, started_at=utc(2, 8, 20), ended_at=utc(2, 19, 40)),  # по 20 минут: время как есть
                ]
            )
            db.commit()

            row = self._row(db, "center-a", "Анна")
            days = {day["work_date"]: day for day in row["days"]}
            self.assertEqual((days[date(2026, 11, 1)]["fact_hours"], days[date(2026, 11, 2)]["fact_hours"]), (12.0, 11.33))
            self.assertEqual(row["fact"]["hours"], 23.33)

    def test_stats_route_lists_the_marks_of_the_month_for_admin_and_only_own_for_staff(self):
        with self.Session() as db:
            self._anchor(db, "anna", date(2026, 10, 30))
            center = self._center(db, "center-a")
            service.generate_month(db, center, 2026, 11)
            anna = self._user(db, "anna")
            db.add(WorkTimeEntry(user_id=anna.id, started_at=utc(1, 9), ended_at=utc(1, 13)))
            db.add(WorkTimeEntry(user_id=self._user(db, "boris").id, started_at=utc(1, 9), ended_at=utc(1, 10)))
            db.commit()

            admin_rows = routes.read_stats(year=2026, month=11, center_id=center.id, viewer=self._user(db, "admin"), db=db).rows
            admin_anna = next(item for item in admin_rows if item.full_name == "Анна")
            self.assertEqual([mark.duration_seconds for mark in admin_anna.marks], [4 * 3600])
            self.assertEqual(admin_anna.marks[0].ended_at, utc(1, 13))

            staff_rows = routes.read_stats(year=2026, month=11, center_id=center.id, viewer=anna, db=db).rows
            self.assertEqual([row.user_id for row in staff_rows], [anna.id])
            self.assertEqual([mark.duration_seconds for mark in staff_rows[0].marks], [4 * 3600], "чужих отметок нет")

    def test_manual_fact_days_are_listed_with_the_marks_and_marked_as_manual(self):
        with self.Session() as db:
            self._anchor(db, "anna", date(2026, 10, 30))
            center = self._center(db, "center-a")
            service.generate_month(db, center, 2026, 11)
            anna = self._user(db, "anna")
            db.add(WorkTimeEntry(user_id=anna.id, started_at=utc(1, 8, 50), ended_at=utc(1, 13)))
            service.put_facts(
                db,
                anna,
                center.id,
                [
                    {"work_date": date(2026, 11, 1), "start_time": time(9), "end_time": time(10)},  # поверх отметки
                    {"work_date": date(2026, 11, 2), "start_time": time(9), "end_time": time(18)},  # день без отметок
                    {"work_date": date(2026, 11, 7), "start_time": time(22), "end_time": time(6)},  # ночная правка
                ],
            )
            db.commit()

            routed = routes.read_stats(year=2026, month=11, center_id=center.id, viewer=self._user(db, "admin"), db=db)

            anna_row = next(item for item in routed.rows if item.full_name == "Анна")
            # Список новые сверху: каждая ручная правка видна, даже без отметок за тот день; отметка остается как была.
            self.assertEqual(
                [(mark.started_at, mark.ended_at, mark.duration_seconds, mark.manual) for mark in anna_row.marks],
                [
                    (utc(7, 22), utc(8, 6), 8 * 3600, True),
                    (utc(2, 9), utc(2, 18), 9 * 3600, True),
                    (utc(1, 9), utc(1, 10), 3600, True),
                    (utc(1, 8, 50), utc(1, 13), 4 * 3600 + 600, False),
                ],
            )
            # Факт тех же дней идет по правкам: 1 ноября 1 ч вместо отметки, 2 ноября 9 ч, 7 ноября 8 ч через полночь.
            hours = {day.work_date: day.fact_hours for day in anna_row.days}
            self.assertEqual((hours[date(2026, 11, 1)], hours[date(2026, 11, 2)], hours[date(2026, 11, 7)]), (1.0, 9.0, 8.0))

    def test_amounts_are_empty_when_rate_is_not_set(self):
        with self.Session() as db:
            service.generate_month(db, self._center(db, "center-a"), 2026, 11)
            db.commit()
            row = self._row(db, "center-a", "Борис")
            self.assertIsNone(row["hourly_rate"])
            self.assertIsNone(row["plan"]["amount"])

    def test_overnight_shift_counts_twelve_hours(self):
        self.assertEqual(service.minutes_to_hours(service.shift_minutes(time(20), time(8))), 12.0)


class AccessTests(WorkScheduleTests):
    def test_table_lists_the_center_staff_in_role_order(self):
        with self.Session() as db:
            grid = self._grid(db, "admin", "center-a")
            self.assertEqual([row.full_name for row in grid.rows], ["Анна", "Ольга", "Борис", "Председатель"])
            self.assertTrue(grid.can_edit)
            self.assertEqual((grid.center.name, grid.center.color), ("Мед-Авто", service.CENTER_PALETTE[0]))
            self.assertEqual([row.full_name for row in self._grid(db, "admin", "center-b").rows], ["Виктор"])

    def test_every_active_center_is_a_tab_even_without_staff(self):
        with self.Session() as db:
            grid = self._grid(db, "admin", "center-c")
            self.assertEqual([item.name for item in grid.centers], ["Мед-Авто", "Медилэнд", "Здравница"])
            self.assertEqual((grid.center.name, grid.rows), ("Здравница", []))

    def test_doctor_and_operator_see_only_own_centers_without_rates(self):
        with self.Session() as db:
            grid = self._grid(db, "anna", None)
            self.assertEqual([item.name for item in grid.centers], ["Мед-Авто"])
            self.assertEqual(grid.center.name, "Мед-Авто")
            self.assertFalse(grid.can_edit)
            self.assertNotIn("hourly_rate", grid.model_dump_json())
            with self.assertRaises(HTTPException) as caught:
                self._grid(db, "anna", "center-b")
            self.assertEqual(caught.exception.status_code, 403)

    def test_doctor_and_operator_get_only_their_own_hours_without_money(self):
        with self.Session() as db:
            center_a = self._center(db, "center-a")
            service.generate_month(db, center_a, 2026, 11)
            anna = self._user(db, "anna")
            db.add(WorkTimeEntry(user_id=anna.id, started_at=utc(1, 9), ended_at=utc(1, 13)))
            db.commit()

            for login in ("anna", "boris"):
                viewer = self._user(db, login)
                routed = routes.read_stats(year=2026, month=11, center_id=center_a.id, viewer=viewer, db=db)
                self.assertEqual([row.user_id for row in routed.rows], [viewer.id], login)
                row = routed.rows[0]
                self.assertEqual((row.hourly_rate, row.plan.amount, row.fact.amount), (None, None, None), login)

            anna_row = routes.read_stats(year=2026, month=11, center_id=center_a.id, viewer=anna, db=db).rows[0]
            self.assertEqual((anna_row.plan.days, anna_row.plan.hours), (16, 192.0))
            self.assertEqual((anna_row.fact.days, anna_row.fact.hours), (1, 4.0))

            viktor = self._user(db, "viktor")
            viktor_rows = routes.read_stats(year=2026, month=11, center_id=None, viewer=viktor, db=db).rows
            self.assertEqual([row.user_id for row in viktor_rows], [viktor.id])
            with self.assertRaises(HTTPException) as caught:
                routes.read_stats(year=2026, month=11, center_id=self._center(db, "center-b").id, viewer=anna, db=db)
            self.assertEqual(caught.exception.status_code, 403)

    def test_admin_stats_still_show_everyone_with_rates(self):
        with self.Session() as db:
            center_a = self._center(db, "center-a")
            routed = routes.read_stats(year=2026, month=11, center_id=center_a.id, viewer=self._user(db, "admin"), db=db)
            rows = {row.full_name: row for row in routed.rows}
            self.assertTrue({"Анна", "Ольга", "Борис", "Председатель"} <= set(rows))
            self.assertEqual(rows["Анна"].hourly_rate, 300.0)
            self.assertIsNone(rows["Борис"].hourly_rate)

    def test_viewers_are_admin_operator_and_doctor_only(self):
        with self.Session() as db:
            self.assertEqual(routes.require_schedule_viewer(current_user=self._user(db, "anna")).login, "anna")
            with self.assertRaises(HTTPException) as caught:
                routes.require_schedule_viewer(current_user=self._user(db, "chair"))
            self.assertEqual(caught.exception.status_code, 403)
            with self.assertRaises(HTTPException):
                routes.require_schedule_viewer(current_user=self._user(db, "guest"))

    def test_only_the_month_table_and_stats_are_open_to_viewers(self):
        for route in (item for item in routes.router.routes if isinstance(item, APIRoute)):
            calls = _dependency_calls(route.dependant)
            if route.path in ("/month", "/stats"):
                self.assertIn(routes.require_schedule_viewer, calls, route.path)
                self.assertNotIn(auth_routes.require_admin, calls, route.path)
            else:
                self.assertIn(auth_routes.require_admin, calls, f"{sorted(route.methods)} {route.path} открыт не только админу")

    def test_guest_is_not_a_schedule_employee(self):
        with self.Session() as db:
            with self.assertRaises(HTTPException) as caught:
                service.load_schedule_user(db, self._user(db, "guest").id)
            self.assertEqual(caught.exception.status_code, 404)
            with self.assertRaises(HTTPException):
                service.load_schedule_user(db, 999999)


class PerCenterTests(WorkScheduleTests):
    def _work_in_both(self, db):
        """Анна работает в Мед-Авто (4/4) и в Медилэнде (5/2 с понедельника 2 ноября, 09:00–18:00)."""
        anna = self._user(db, "anna")
        center_b = self._center(db, "center-b")
        anna.extra_centers = [center_b]
        add_schedule(anna, center_b, "5/2", anchor=date(2026, 11, 2), start=time(9), end=time(18))
        db.commit()
        return anna

    def test_one_employee_has_separate_schedules_in_each_center(self):
        with self.Session() as db:
            self._work_in_both(db)
            anna_a = next(row for row in self._grid(db, "admin", "center-a").rows if row.full_name == "Анна")
            anna_b = next(row for row in self._grid(db, "admin", "center-b").rows if row.full_name == "Анна")
            self.assertEqual((anna_a.pattern, anna_a.shift_start, anna_a.shift_end), ("4/4", "08:00", "20:00"))
            self.assertEqual((anna_b.pattern, anna_b.shift_start, anna_b.shift_end), ("5/2", "09:00", "18:00"))

    def test_account_with_both_centers_is_shown_in_each_table(self):
        with self.Session() as db:
            self._work_in_both(db)
            for code in ("center-a", "center-b"):
                self.assertIn("Анна", [row.full_name for row in self._grid(db, "admin", code).rows])
            self.assertEqual([item.name for item in self._grid(db, "anna", None).centers], ["Мед-Авто", "Медилэнд"])

    def test_same_day_shifts_in_two_centers_are_marked_in_both_tables(self):
        with self.Session() as db:
            self._work_in_both(db)
            service.generate_month(db, self._center(db, "center-a"), 2026, 11)
            service.generate_month(db, self._center(db, "center-b"), 2026, 11)
            db.commit()
            in_a = {day.work_date.day: day for day in self._grid_row(db, "anna", "center-a").days}
            in_b = {day.work_date.day: day for day in self._grid_row(db, "anna", "center-b").days}
            # 2–4 ноября смены стоят в обоих медцентрах; 1 ноября только в Мед-Авто, 5 ноября только в Медилэнде.
            self.assertEqual([item.center_name for item in in_a[2].conflicts], ["Медилэнд"])
            self.assertEqual([item.center_name for item in in_b[3].conflicts], ["Мед-Авто"])
            self.assertEqual(in_a[1].conflicts, [])
            self.assertEqual(in_b[5].conflicts, [])
            self.assertEqual((in_a[2].conflicts[0].start_time, in_a[2].conflicts[0].end_time), ("09:00", "18:00"))

    def test_absence_in_another_center_is_not_a_conflict(self):
        with self.Session() as db:
            anna = self._work_in_both(db)
            center_b = self._center(db, "center-b")
            service.generate_month(db, self._center(db, "center-a"), 2026, 11)
            service.generate_month(db, center_b, 2026, 11)
            service.put_absence(db, anna, center_b.id, [date(2026, 11, 2)], "sick")
            db.commit()
            in_a = {day.work_date.day: day for day in self._grid_row(db, "anna", "center-a").days}
            self.assertEqual(in_a[2].conflicts, [])

    def test_viewer_sees_conflicts_only_inside_own_centers(self):
        with self.Session() as db:
            self._work_in_both(db)
            service.generate_month(db, self._center(db, "center-a"), 2026, 11)
            service.generate_month(db, self._center(db, "center-b"), 2026, 11)
            db.commit()
            admin_view = {day.work_date.day: day for day in self._grid_row(db, "anna", "center-a", "admin").days}
            olga_view = {day.work_date.day: day for day in self._grid_row(db, "anna", "center-a", "olga").days}
            self.assertEqual(len(admin_view[2].conflicts), 1)
            self.assertEqual(olga_view[2].conflicts, [])

    def test_days_of_one_center_do_not_leak_into_another(self):
        with self.Session() as db:
            anna = self._work_in_both(db)
            center_b = self._center(db, "center-b")
            service.put_day(db, anna, center_b.id, date(2026, 11, 15), "shift", time(9), time(18))
            db.commit()
            self.assertIsNone(self._row_days(db, "anna", "center-a").get(15))
            self.assertEqual(self._row_days(db, "anna", "center-b").get(15), ("shift", None))


class MigrationTests(unittest.TestCase):
    def test_model_and_migration_agree_on_the_per_center_schema(self):
        self.assertIn("center_id", Base.metadata.tables["staff_schedule_days"].columns)
        self.assertIn("staff_center_schedules", Base.metadata.tables)
        self.assertNotIn("schedule_pattern", Base.metadata.tables["users"].columns)
        migration = (Path(__file__).resolve().parents[1] / "migrations/versions/20261107_0030_per_center_schedules.py").read_text(encoding="utf-8")
        self.assertIn('down_revision: str | None = "20261106_0029"', migration)
        self.assertIn("staff_center_schedules", migration)


if __name__ == "__main__":
    unittest.main()
