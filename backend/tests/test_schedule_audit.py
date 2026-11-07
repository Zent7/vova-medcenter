"""Журнал аудита графика и ставки: каждая правка админа оставляет запись в той же транзакции.

Запись идет с entity_type «staff_schedule» и id сотрудника, а в payload — что было и что стало.
Запись появляется, только если правка что-то поменяла: повторное сохранение того же дня, того же
отпуска или той же ставки в журнал не попадает, и отказ в правке (ошибка проверки) тоже ничего
не пишет. «Назначить первую смену» — отдельное действие админа, оно пишется каждый раз.
График у каждого медцентра свой: запись несет медцентр, которого касается правка.
Читать журнал может только админ (см. test_admin_only_access).
"""

from datetime import date, time
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from unittest import mock

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes import audit_logs as audit_routes  # noqa: E402
from app.api.v1.routes import staff as staff_routes  # noqa: E402
from app.api.v1.routes import work_schedule as schedule_routes  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.staff_center_schedule import StaffCenterSchedule  # noqa: E402
from app.models.user import Role, User  # noqa: E402
from app.schemas.user_admin import StaffCenterScheduleCreate, StaffScheduleUpdate, StaffUserCreate  # noqa: E402
from app.schemas.work_schedule import (  # noqa: E402
    WorkScheduleAbsenceCreate,
    WorkScheduleDayUpdate,
    WorkScheduleFactItem,
    WorkScheduleFactsUpdate,
    WorkScheduleFirstShift,
)
from app.services import work_schedule as service  # noqa: E402


ROLE_CODES = ("admin", "operator", "doctor", "chairman")


class ScheduleAuditTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        with self.Session() as db:
            roles = {code: Role(code=code, name=code) for code in ROLE_CODES}
            db.add_all(roles.values())
            db.flush()
            center = Center(code="center-a", name="Центр А")
            db.add(center)
            db.flush()
            admin = User(
                role_id=roles["admin"].id,
                login="admin",
                password_hash=hash_password("admin123"),
                full_name="Евгений",
                is_active=True,
            )
            boris = User(
                role_id=roles["doctor"].id,
                login="boris",
                password_hash=hash_password("boris123"),
                full_name="Борис Врачов",
                is_active=True,
                center_id=center.id,
                hourly_rate=Decimal("300"),
                center_schedules=[
                    StaffCenterSchedule(
                        center_id=center.id, schedule_pattern="2/2", schedule_start=time(9), schedule_end=time(20)
                    )
                ],
            )
            db.add_all([admin, boris])
            db.commit()
            self.center_id = center.id
            self.admin_id = admin.id
            self.boris_id = boris.id

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _entries(self, db, action=None):
        query = select(AuditLog).where(AuditLog.entity_type == "staff_schedule").order_by(AuditLog.id)
        if action is not None:
            query = query.where(AuditLog.action == action)
        return list(db.execute(query).scalars())

    def _admin(self, db):
        return db.get(User, self.admin_id)

    def _boris(self, db):
        return db.get(User, self.boris_id)

    def _boris_schedule(self, db):
        return self._boris(db).schedule_in(self.center_id)

    def _item(self, pattern="2/2", start=time(9), end=time(20)) -> StaffCenterScheduleCreate:
        return StaffCenterScheduleCreate(center_id=self.center_id, pattern=pattern, shift_start=start, shift_end=end)

    def _update_schedules(self, db, schedules, hourly_rate=None):
        return staff_routes.update_staff_schedules(
            user_id=self.boris_id,
            payload=StaffScheduleUpdate(schedules=schedules, hourly_rate=hourly_rate),
            background_tasks=BackgroundTasks(),
            admin=self._admin(db),
            db=db,
        )

    def _update_day(self, db, work_date, kind):
        schedule_routes.update_day(
            user_id=self.boris_id,
            work_date=work_date,
            payload=WorkScheduleDayUpdate(kind=kind, start_time=None, end_time=None),
            background_tasks=BackgroundTasks(),
            center_id=self.center_id,
            admin=self._admin(db),
            db=db,
        )

    def _clear_day(self, db, work_date):
        schedule_routes.clear_day(
            user_id=self.boris_id,
            work_date=work_date,
            background_tasks=BackgroundTasks(),
            center_id=self.center_id,
            admin=self._admin(db),
            db=db,
        )

    def test_new_schedule_is_logged_with_center_pattern_hours_and_rate(self):
        with self.Session() as db:
            payload = StaffUserCreate(
                login="viktor",
                password="viktor123",
                full_name="Виктор",
                role_code="doctor",
                center_ids=[self.center_id],
                schedules=[self._item("3/3", time(8), time(20))],
                hourly_rate=Decimal("250"),
            )
            created = staff_routes.create_staff(
                payload=payload, background_tasks=BackgroundTasks(), current_user=self._admin(db), db=db
            )

            (entry,) = self._entries(db, "schedule_create")
            self.assertEqual(entry.entity_id, created.id)
            self.assertEqual(entry.user_id, self.admin_id)
            self.assertEqual(entry.center_id, self.center_id)
            self.assertEqual(
                entry.payload_json,
                {"staff": "Виктор", "center": "Центр А", "schedule": "3/3, 08:00-20:00", "hourly_rate": 250.0},
            )

    def test_staff_without_schedule_is_not_logged(self):
        with self.Session() as db:
            payload = StaffUserCreate(
                login="olga", password="olga123", full_name="Ольга", role_code="operator", center_ids=[self.center_id]
            )
            staff_routes.create_staff(payload=payload, background_tasks=BackgroundTasks(), current_user=self._admin(db), db=db)
            self.assertEqual(self._entries(db), [])

    def test_changed_times_and_rate_are_logged_as_separate_entries(self):
        with self.Session() as db:
            # Первая смена уже назначена: сохранение того же графика ничего не пишет.
            self._boris_schedule(db).schedule_anchor_date = date(2026, 11, 2)
            db.commit()
            # Те же время и ставка: правки нет, записи нет.
            self._update_schedules(db, [self._item()], Decimal("300"))
            self.assertEqual(self._entries(db), [])

            # Только ставка: одна запись rate_update.
            self._update_schedules(db, [self._item()], Decimal("320"))
            self.assertEqual(self._entries(db, "schedule_update"), [])
            (rate,) = self._entries(db, "rate_update")
            self.assertEqual(rate.payload_json, {"staff": "Борис Врачов", "before": 300.0, "after": 320.0})

            # Время и ставка вместе: две записи, у каждой свое было и стало.
            self._update_schedules(db, [self._item("3/3", time(8), time(20))], Decimal("350"))
            (schedule,) = self._entries(db, "schedule_update")
            self.assertEqual(
                schedule.payload_json,
                {
                    "staff": "Борис Врачов",
                    "center": "Центр А",
                    "before": "2/2, 09:00-20:00",
                    "after": "3/3, 08:00-20:00",
                },
            )
            self.assertEqual(
                self._entries(db, "rate_update")[-1].payload_json,
                {"staff": "Борис Врачов", "before": 320.0, "after": 350.0},
            )

            # График снят целиком: ставка тоже пустеет.
            self._update_schedules(db, [], None)
            self.assertEqual(self._entries(db, "schedule_update")[-1].payload_json["after"], "без графика")
            self.assertEqual(
                self._entries(db, "rate_update")[-1].payload_json,
                {"staff": "Борис Врачов", "before": 350.0, "after": None},
            )

    def test_day_edit_is_logged_with_what_it_was_and_what_it_is_now(self):
        with self.Session() as db:
            service.put_day(db, self._boris(db), self.center_id, date(2026, 11, 5), "shift", time(9), time(20))
            db.commit()

            self._update_day(db, date(2026, 11, 5), "dayoff")
            (entry,) = self._entries(db, "day_update")
            self.assertEqual(
                entry.payload_json,
                {
                    "center": "Центр А",
                    "date": "2026-11-05",
                    "before": {"kind": "shift", "start": "09:00", "end": "20:00", "fact_start": None, "fact_end": None},
                    "after": {"kind": "dayoff", "start": None, "end": None, "fact_start": None, "fact_end": None},
                },
            )

            # Тот же отгул еще раз: ничего не поменялось, новой записи нет.
            self._update_day(db, date(2026, 11, 5), "dayoff")
            self.assertEqual(len(self._entries(db, "day_update")), 1)

    def test_rejected_day_edit_leaves_no_record(self):
        with self.Session() as db:
            with self.assertRaises(HTTPException):
                self._update_day(db, date(2026, 11, 5), "shift")  # смена без времени
            self.assertEqual(self._entries(db), [])

    def test_cleared_day_is_logged_once(self):
        with self.Session() as db:
            service.put_day(db, self._boris(db), self.center_id, date(2026, 11, 6), "shift", time(9), time(20))
            db.commit()

            self._clear_day(db, date(2026, 11, 6))
            (entry,) = self._entries(db, "day_clear")
            self.assertEqual(entry.payload_json["before"]["kind"], "shift")
            self.assertIsNone(entry.payload_json["after"])

            self._clear_day(db, date(2026, 11, 6))  # день уже пуст
            self.assertEqual(len(self._entries(db, "day_clear")), 1)

    def test_absence_records_how_the_period_looked_before(self):
        with self.Session() as db:
            boris = self._boris(db)
            service.put_day(db, boris, self.center_id, date(2026, 11, 10), "shift", time(9), time(20))
            service.put_day(db, boris, self.center_id, date(2026, 11, 11), "dayoff", None, None)
            db.commit()

            schedule_routes.add_absence(
                user_id=self.boris_id,
                payload=WorkScheduleAbsenceCreate(
                    kind="vacation", date_from=date(2026, 11, 10), date_to=date(2026, 11, 12)
                ),
                background_tasks=BackgroundTasks(),
                center_id=self.center_id,
                admin=self._admin(db),
                db=db,
            )
            (entry,) = self._entries(db, "absence_add")
            self.assertEqual(
                entry.payload_json,
                {
                    "center": "Центр А",
                    "from": "2026-11-10",
                    "to": "2026-11-12",
                    "kind": "vacation",
                    "days": 3,
                    "before": {"shift": 1, "dayoff": 1, "empty": 1},
                },
            )

    def test_repeated_absence_is_not_logged_again(self):
        with self.Session() as db:
            request = WorkScheduleAbsenceCreate(kind="sick", date_from=date(2026, 11, 17), date_to=date(2026, 11, 18))
            for _ in range(2):
                schedule_routes.add_absence(
                    user_id=self.boris_id,
                    payload=request,
                    background_tasks=BackgroundTasks(),
                    center_id=self.center_id,
                    admin=self._admin(db),
                    db=db,
                )
            (entry,) = self._entries(db, "absence_add")
            self.assertEqual(entry.payload_json["days"], 2)
            self.assertEqual(entry.payload_json["before"], {"empty": 2})

    def test_first_shift_started_by_saving_the_schedule_is_logged_once(self):
        with self.Session() as db, mock.patch("app.services.work_schedule.local_today", return_value=date(2026, 11, 7)):
            # График есть, первой смены нет: сохранение ставит ее на сегодня и пишет в журнал.
            self._update_schedules(db, [self._item()], Decimal("300"))
            (entry,) = self._entries(db, "first_shift")
            self.assertIsNone(entry.payload_json["anchor_before"])
            self.assertEqual(entry.payload_json["work_date"], "2026-11-07")
            self.assertGreater(entry.payload_json["created"], 0)
            self.assertEqual(self._boris_schedule(db).schedule_anchor_date, date(2026, 11, 7))

            # Второе сохранение первую смену не трогает и в журнал ничего не добавляет.
            self._update_schedules(db, [self._item()], Decimal("300"))
            self.assertEqual(len(self._entries(db, "first_shift")), 1)

    def test_first_shift_is_logged_with_the_previous_start(self):
        with self.Session() as db:
            for work_date in (date(2026, 11, 3), date(2026, 11, 10)):
                schedule_routes.start_first_shift(
                    user_id=self.boris_id,
                    payload=WorkScheduleFirstShift(work_date=work_date),
                    background_tasks=BackgroundTasks(),
                    center_id=self.center_id,
                    admin=self._admin(db),
                    db=db,
                )
            first, second = self._entries(db, "first_shift")
            self.assertIsNone(first.payload_json["anchor_before"])
            self.assertEqual(first.payload_json["work_date"], "2026-11-03")
            self.assertGreater(first.payload_json["created"], 0)
            self.assertEqual(second.payload_json["anchor_before"], "2026-11-03")
            self.assertEqual(second.payload_json["work_date"], "2026-11-10")

    def test_fact_is_logged_only_for_days_whose_fact_changed(self):
        with self.Session() as db:
            boris = self._boris(db)
            service.put_day(db, boris, self.center_id, date(2026, 11, 3), "shift", time(9), time(20))
            service.put_day(db, boris, self.center_id, date(2026, 11, 4), "shift", time(9), time(20))
            service.put_facts(
                db,
                boris,
                self.center_id,
                [{"work_date": date(2026, 11, 3), "start_time": time(9, 30), "end_time": time(20)}],
            )
            db.commit()

            schedule_routes.update_facts(
                user_id=self.boris_id,
                payload=WorkScheduleFactsUpdate(
                    items=[
                        WorkScheduleFactItem(work_date=date(2026, 11, 3), start_time=time(9, 30), end_time=time(20)),
                        WorkScheduleFactItem(work_date=date(2026, 11, 4), start_time=time(9), end_time=time(21)),
                    ]
                ),
                background_tasks=BackgroundTasks(),
                center_id=self.center_id,
                admin=self._admin(db),
                db=db,
            )
            (entry,) = self._entries(db, "facts_update")
            self.assertEqual(
                entry.payload_json,
                {"center": "Центр А", "items": [{"date": "2026-11-04", "before": None, "after": "09:00-21:00"}]},
            )

    def test_month_generation_is_logged_for_each_employee_who_got_shifts(self):
        with self.Session() as db:
            self._boris_schedule(db).schedule_anchor_date = date(2026, 11, 1)
            operator = db.execute(select(Role).where(Role.code == "operator")).scalar_one()
            # У Анны график есть, а первой смены нет: в журнал она не попадает, в ответе — в списке «без первой смены».
            db.add(
                User(
                    role_id=operator.id,
                    login="anna",
                    password_hash=hash_password("anna123"),
                    full_name="Анна Операторова",
                    is_active=True,
                    center_id=self.center_id,
                    center_schedules=[
                        StaffCenterSchedule(
                            center_id=self.center_id, schedule_pattern="4/4", schedule_start=time(8), schedule_end=time(20)
                        )
                    ],
                )
            )
            db.commit()

            result = service.generate_month(db, db.get(Center, self.center_id), 2026, 11, actor_id=self.admin_id)

            (entry,) = self._entries(db, "month_generate")
            self.assertEqual(entry.entity_id, self.boris_id)
            self.assertEqual(entry.user_id, self.admin_id)
            self.assertEqual(
                entry.payload_json,
                {"center": "Центр А", "year": 2026, "month": 11, "created": result["created"]},
            )
            self.assertEqual(result["users_without_start"], ["Анна Операторова"])

    def test_admin_reads_the_entries_with_the_author_name(self):
        with self.Session() as db:
            self._update_schedules(db, [self._item()], Decimal("320"))
            rows = audit_routes.list_audit_logs(
                entity_type="staff_schedule", entity_id=self.boris_id, action="rate_update", limit=10, db=db
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].user_name, "Евгений")
            self.assertEqual(rows[0].payload_json, {"staff": "Борис Врачов", "before": 300.0, "after": 320.0})
            self.assertEqual(rows[0].entity_name, "Борис Врачов")

            # В записи про день имени сотрудника нет: его берем из учетки.
            self._update_day(db, date(2026, 11, 5), "dayoff")
            day = audit_routes.list_audit_logs(
                entity_type="staff_schedule", entity_id=self.boris_id, action="day_update", limit=10, db=db
            )
            self.assertEqual(day[0].entity_name, "Борис Врачов")


class StaffDeleteAuditTests(unittest.TestCase):
    """Стирание учетки с графиком или ставкой попадает в журнал; отключение вместо стирания — нет."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(dbapi_connection, _record):
            # Как в PostgreSQL: без этого SQLite стер бы учетку, на которую ссылаются дни графика.
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        with self.Session() as db:
            center = Center(code="center-a", name="Центр А")
            admin_role = Role(code="admin", name="admin")
            doctor_role = Role(code="doctor", name="doctor")
            db.add_all([center, admin_role, doctor_role])
            db.flush()
            self.center_id = center.id
            db.add(
                User(
                    role_id=admin_role.id,
                    login="admin",
                    password_hash=hash_password("admin123"),
                    full_name="Евгений",
                    is_active=True,
                )
            )
            for login, full_name, scheduled in (
                ("clean", "Без записей", True),
                ("plain", "Без графика", False),
                ("worked", "С записями", True),
            ):
                db.add(
                    User(
                        role_id=doctor_role.id,
                        login=login,
                        password_hash=hash_password("secret123"),
                        full_name=full_name,
                        is_active=True,
                        center_id=center.id,
                        hourly_rate=Decimal("300") if scheduled else None,
                        center_schedules=(
                            [
                                StaffCenterSchedule(
                                    center_id=center.id,
                                    schedule_pattern="2/2",
                                    schedule_start=time(9),
                                    schedule_end=time(20),
                                )
                            ]
                            if scheduled
                            else []
                        ),
                    )
                )
            db.commit()

    def tearDown(self):
        self.engine.dispose()

    def _user(self, db, login):
        return db.execute(select(User).where(User.login == login)).scalar_one()

    def _staff_delete_entries(self, db):
        return list(db.execute(select(AuditLog).where(AuditLog.action == "staff_delete")).scalars())

    def test_deleted_account_is_logged_with_its_schedule_and_rate(self):
        with self.Session() as db:
            admin_id = self._user(db, "admin").id
            clean_id = self._user(db, "clean").id

            result = staff_routes.delete_staff_user(user_id=clean_id, current_user=self._user(db, "admin"), db=db)

            self.assertTrue(result.deleted)
            (entry,) = self._staff_delete_entries(db)
            self.assertEqual(entry.entity_id, clean_id)
            self.assertEqual(entry.user_id, admin_id)
            self.assertEqual(entry.center_id, self.center_id)
            self.assertEqual(
                entry.payload_json,
                {"staff": "Без записей", "schedule": "Центр А: 2/2, 09:00-20:00", "hourly_rate": 300.0},
            )

    def test_deleted_account_without_schedule_is_not_logged(self):
        with self.Session() as db:
            plain_id = self._user(db, "plain").id

            result = staff_routes.delete_staff_user(user_id=plain_id, current_user=self._user(db, "admin"), db=db)

            self.assertTrue(result.deleted)
            self.assertEqual(self._staff_delete_entries(db), [])

    def test_account_kept_as_disabled_is_not_logged_as_deleted(self):
        with self.Session() as db:
            worked = self._user(db, "worked")
            service.put_day(db, worked, self.center_id, date(2026, 11, 5), "dayoff", None, None)
            db.commit()
            worked_id = worked.id

            result = staff_routes.delete_staff_user(user_id=worked_id, current_user=self._user(db, "admin"), db=db)

            self.assertFalse(result.deleted)
            self.assertFalse(db.get(User, worked_id).is_active)
            self.assertEqual(self._staff_delete_entries(db), [])


if __name__ == "__main__":
    unittest.main()
