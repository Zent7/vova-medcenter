"""Статус «На работу / С работы»: отметки, сводка план-факт по дням и только собственные данные.

Отметка без «С работы» считается открытой и идет до текущего момента. План дня берется из
графика, факт — из отметок; отметка через полночь делится по местным дням.
"""

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes import work_status as routes  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.staff_center_schedule import StaffCenterSchedule  # noqa: E402
from app.models.staff_schedule_day import StaffScheduleDay  # noqa: E402
from app.models.user import Role, User  # noqa: E402
from app.models.work_time_entry import WorkTimeEntry  # noqa: E402
from app.services import work_status as service  # noqa: E402
from app.services.work_schedule import start_plan_if_missing  # noqa: E402


# Москва без летнего времени с 2014 года, поэтому фиксированное смещение +3 надежно.
MSK = timezone(timedelta(hours=3))


def msk(day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=MSK)


def utc(day: int, hour: int = 0, minute: int = 0) -> datetime:
    """Момент, как его записывают в таблицу: в UTC (SQLite не переводит часовой пояс сам)."""
    return msk(day, hour, minute).astimezone(timezone.utc)


class MinutesAndPlanTests(unittest.TestCase):
    def test_a_mark_across_midnight_is_split_by_local_day(self):
        minutes = service.minutes_by_local_day(msk(2, 21), msk(3, 2), date(2026, 11, 1), date(2026, 11, 30))

        self.assertEqual(minutes, {date(2026, 11, 2): 180, date(2026, 11, 3): 120})

    def test_only_the_days_of_the_period_are_counted(self):
        minutes = service.minutes_by_local_day(msk(2, 21), msk(3, 2), date(2026, 11, 3), date(2026, 11, 30))

        self.assertEqual(minutes, {date(2026, 11, 3): 120})

    def test_times_without_a_zone_from_sqlite_count_as_utc(self):
        # 21:00 по Москве — это 18:00 UTC, 02:00 по Москве — это 23:00 UTC предыдущего дня.
        minutes = service.minutes_by_local_day(
            datetime(2026, 11, 2, 18), datetime(2026, 11, 2, 23), date(2026, 11, 1), date(2026, 11, 30)
        )

        self.assertEqual(minutes, {date(2026, 11, 2): 180, date(2026, 11, 3): 120})

    def test_plan_of_a_night_shift_counts_through_midnight(self):
        self.assertEqual(service.plan_minutes(StaffScheduleDay(kind="shift", start_time=time(20), end_time=time(8))), 720)
        self.assertEqual(service.plan_minutes(StaffScheduleDay(kind="vacation")), 0)
        self.assertEqual(service.plan_minutes(None), 0)


class WorkStatusTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        with self.Session() as db:
            roles = {code: Role(code=code, name=code) for code in ("operator", "doctor")}
            db.add_all(roles.values())
            db.flush()
            db.add_all(
                [
                    User(
                        role_id=roles["operator"].id,
                        login="anna",
                        password_hash=hash_password("anna123"),
                        full_name="Анна",
                        is_active=True,
                    ),
                    User(
                        role_id=roles["doctor"].id,
                        login="boris",
                        password_hash=hash_password("boris123"),
                        full_name="Борис",
                        is_active=True,
                    ),
                ]
            )
            db.commit()

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _user(self, db, login: str) -> User:
        return db.execute(select(User).where(User.login == login)).scalar_one()


class PlanInStatusTests(WorkStatusTests):
    def test_a_schedule_saved_without_first_shift_shows_its_plan_from_today(self):
        # Так сохраняется график без первой смены: план на сегодня и дальше, в «Статусе» есть столбцы плана.
        with self.Session() as db:
            center = Center(code="center-a", name="Мед-Авто")
            db.add(center)
            db.flush()
            anna = self._user(db, "anna")
            anna.center_id = center.id
            schedule = StaffCenterSchedule(center_id=center.id, schedule_pattern="2/2", schedule_start=time(8), schedule_end=time(20))
            anna.center_schedules.append(schedule)
            db.flush()
            start_plan_if_missing(db, anna, schedule, actor_id=None, today=date(2026, 11, 7))
            db.commit()

            payload = service.month_payload(db, anna, 2026, 11, msk(7, 10))

            days = {day["work_date"]: day for day in payload["days"]}
            self.assertEqual(days[date(2026, 11, 6)]["plan_hours"], 0)  # до первой смены плана нет
            self.assertEqual(days[date(2026, 11, 7)]["plan_hours"], 12.0)
            self.assertEqual(days[date(2026, 11, 9)]["plan_hours"], 0)  # отдых по 2/2
            self.assertGreater(payload["totals"]["plan_hours"], 0)


class MarksTests(WorkStatusTests):
    def test_a_second_start_keeps_the_open_mark_and_stop_closes_it(self):
        with self.Session() as db:
            anna = self._user(db, "anna")
            first = service.start_work(db, anna, msk(3, 9))
            second = service.start_work(db, anna, msk(3, 9, 5))
            self.assertIs(first, second)

            service.stop_work(db, anna, msk(3, 18, 30))
            db.commit()

            entries = db.execute(select(WorkTimeEntry)).scalars().all()
            self.assertEqual(len(entries), 1)
            self.assertIsNotNone(entries[0].ended_at)
            self.assertIsNone(service.open_entry(db, anna))

    def test_stop_without_an_open_mark_does_nothing(self):
        with self.Session() as db:
            anna = self._user(db, "anna")

            self.assertIsNone(service.stop_work(db, anna, msk(3, 18)))
            self.assertEqual(db.execute(select(WorkTimeEntry)).scalars().all(), [])

    def test_month_summary_compares_marks_with_the_schedule(self):
        with self.Session() as db:
            anna = self._user(db, "anna")
            db.add(StaffScheduleDay(user_id=anna.id, work_date=date(2026, 11, 3), kind="shift",
                                    start_time=time(9), end_time=time(20), source="manual"))
            db.add(StaffScheduleDay(user_id=anna.id, work_date=date(2026, 11, 4), kind="vacation", source="manual"))
            db.add(WorkTimeEntry(user_id=anna.id, started_at=utc(3, 9), ended_at=utc(3, 21, 30)))  # 12,5 ч при плане 11
            db.add(WorkTimeEntry(user_id=anna.id, started_at=utc(6, 10), ended_at=utc(6, 12)))  # без графика: 2 ч
            db.commit()

            payload = service.month_payload(db, anna, 2026, 11, msk(7, 12))

        days = {day["work_date"]: day for day in payload["days"]}
        self.assertEqual(payload["days_in_month"], 30)
        self.assertEqual(
            (days[date(2026, 11, 3)]["plan_hours"], days[date(2026, 11, 3)]["fact_hours"], days[date(2026, 11, 3)]["overtime_hours"]),
            (11.0, 12.5, 1.5),
        )
        self.assertEqual(days[date(2026, 11, 4)]["kind"], "vacation")
        self.assertEqual(days[date(2026, 11, 4)]["plan_hours"], 0.0)
        self.assertEqual(days[date(2026, 11, 6)]["overtime_hours"], 2.0)
        self.assertEqual(payload["totals"], {"plan_hours": 11.0, "fact_hours": 14.5, "overtime_hours": 3.5})
        self.assertIsNone(payload["open"])

    def test_an_open_mark_counts_up_to_now(self):
        with self.Session() as db:
            anna = self._user(db, "anna")
            db.add(WorkTimeEntry(user_id=anna.id, started_at=utc(7, 10)))
            db.commit()

            payload = service.month_payload(db, anna, 2026, 11, msk(7, 10, 45))

        self.assertEqual(payload["open"]["elapsed_seconds"], 45 * 60)
        days = {day["work_date"]: day for day in payload["days"]}
        self.assertEqual(days[date(2026, 11, 7)]["fact_hours"], 0.75)
        self.assertEqual(payload["totals"]["fact_hours"], 0.75)

    def test_marks_of_another_employee_are_not_shown(self):
        with self.Session() as db:
            boris = self._user(db, "boris")
            anna = self._user(db, "anna")
            db.add(WorkTimeEntry(user_id=boris.id, started_at=utc(7, 9)))
            db.commit()

            payload = service.month_payload(db, anna, 2026, 11, msk(7, 12))

        self.assertIsNone(payload["open"])
        self.assertEqual(payload["totals"]["fact_hours"], 0.0)

    def test_fact_minutes_by_user_groups_marks_by_employee_and_local_day(self):
        with self.Session() as db:
            anna = self._user(db, "anna")
            boris = self._user(db, "boris")
            anna_id, boris_id = anna.id, boris.id
            db.add_all(
                [
                    WorkTimeEntry(user_id=anna_id, started_at=utc(2, 21), ended_at=utc(3, 2)),  # через полночь
                    WorkTimeEntry(user_id=boris_id, started_at=utc(7, 9), ended_at=utc(7, 10)),
                    WorkTimeEntry(user_id=anna_id, started_at=utc(7, 9)),  # открыта: считается до now
                ]
            )
            db.commit()

            counted = service.fact_minutes_by_user(db, date(2026, 11, 1), date(2026, 11, 30), msk(7, 10, 30))

        self.assertEqual(counted[anna_id], {date(2026, 11, 2): 180, date(2026, 11, 3): 120, date(2026, 11, 7): 90})
        self.assertEqual(counted[boris_id], {date(2026, 11, 7): 60})

    def test_routes_start_and_stop_the_marks_of_the_current_user(self):
        with self.Session() as db:
            anna = self._user(db, "anna")

            started = routes.start_work(current_user=anna, db=db)
            self.assertIsNotNone(started.open)

            stopped = routes.stop_work(current_user=anna, db=db)
            self.assertIsNone(stopped.open)

            month = routes.read_my_status(year=2026, month=11, current_user=anna, db=db)
            self.assertEqual(month.days_in_month, 30)
            self.assertEqual(len(month.days), 30)


class EarlyLeaveRoundingTests(WorkStatusTests):
    """Уход раньше конца смены не больше чем на 15 минут считается по плану; дальше время идет как есть."""

    def _day_3_november(self, leave, start=(9, 0), now=msk(7, 12)) -> dict:
        """Смена 3 ноября с 09:00 до 18:00; отметка с start до leave (часы, минуты), без leave — открыта."""
        with self.Session() as db:
            anna = self._user(db, "anna")
            db.add(
                StaffScheduleDay(
                    user_id=anna.id, work_date=date(2026, 11, 3), kind="shift",
                    start_time=time(9), end_time=time(18), source="manual",
                )
            )
            ended = None if leave is None else utc(3, *leave)
            db.add(WorkTimeEntry(user_id=anna.id, started_at=utc(3, *start), ended_at=ended))
            db.commit()

            payload = service.month_payload(db, anna, 2026, 11, now)

        return {day["work_date"]: day for day in payload["days"]}[date(2026, 11, 3)]

    def test_leaving_ten_minutes_early_counts_the_whole_shift(self):
        day = self._day_3_november((17, 50))

        self.assertEqual((day["plan_hours"], day["fact_hours"], day["overtime_hours"]), (9.0, 9.0, 0.0))

    def test_leaving_exactly_fifteen_minutes_early_counts_the_whole_shift(self):
        self.assertEqual(self._day_3_november((17, 45))["fact_hours"], 9.0)

    def test_leaving_sixteen_minutes_early_counts_the_time_on_the_counter(self):
        self.assertEqual(self._day_3_november((17, 44))["fact_hours"], 8.73)  # 8 ч 44 мин

    def test_leaving_after_the_end_is_overtime_as_before(self):
        day = self._day_3_november((18, 20))

        self.assertEqual((day["fact_hours"], day["overtime_hours"]), (9.33, 0.33))

    def test_a_mark_that_is_still_open_is_not_rounded(self):
        # Сотрудник еще на работе: в 17:50 факт 8 ч 50 мин, а не конец смены.
        self.assertEqual(self._day_3_november(None, now=msk(3, 17, 50))["fact_hours"], 8.83)

    def test_a_mark_that_starts_in_the_last_fifteen_minutes_is_not_rounded(self):
        self.assertEqual(self._day_3_november((17, 55), start=(17, 50))["fact_hours"], 0.08)  # 5 минут как есть

    def test_night_shift_that_ends_early_in_the_next_month_is_rounded_too(self):
        with self.Session() as db:
            anna = self._user(db, "anna")
            db.add(
                StaffScheduleDay(
                    user_id=anna.id, work_date=date(2026, 10, 31), kind="shift",
                    start_time=time(20), end_time=time(8), source="manual",
                )
            )
            # Смена 31 октября с 20:00 до 08:00; отметка кончилась 1 ноября в 07:50 и округляется до 08:00.
            started = datetime(2026, 10, 31, 20, tzinfo=MSK).astimezone(timezone.utc)
            db.add(WorkTimeEntry(user_id=anna.id, started_at=started, ended_at=utc(1, 7, 50)))
            db.commit()

            payload = service.month_payload(db, anna, 2026, 11, msk(7, 12))

        self.assertEqual({day["work_date"]: day for day in payload["days"]}[date(2026, 11, 1)]["fact_hours"], 8.0)


if __name__ == "__main__":
    unittest.main()
