"""Уведомления админам: адреса админов, отправка в фоне и триггеры.

Письмо уходит на почту активных админов (учетка с почтой в «Сотрудники»). Отправка идет в фоне
после ответа, без SMTP ничего не уходит, а ошибка почты не ломает сохранение изменения.
Триггеры: правка дня графика, первая смена, создание графика, смена времени смены, ФИО клиента.
"""

from datetime import date, time
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
from app.api.v1.routes import clients as clients_routes  # noqa: E402
from app.api.v1.routes import staff as staff_routes  # noqa: E402
from app.api.v1.routes import work_schedule as schedule_routes  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.user import Role, User  # noqa: E402
from app.schemas.client import ClientCreate, ClientUpdate  # noqa: E402
from app.schemas.user_admin import (  # noqa: E402
    StaffEmailUpdate,
    StaffScheduleCreate,
    StaffScheduleUpdate,
    StaffUserCreate,
)
from app.schemas.work_schedule import WorkScheduleDayUpdate  # noqa: E402
from app.services import notifications  # noqa: E402


# Настоящая отправка, сохраненная до подмены в тестах: без SMTP она ничего не шлет.
REAL_SEND_EMAIL = notifications.send_email


def schedule(pattern: str = "2/2", start: time = time(9), end: time = time(20)) -> StaffScheduleCreate:
    return StaffScheduleCreate(pattern=pattern, shift_start=start, shift_end=end)


def client_create(last_name: str, center_ids: list[int]) -> ClientCreate:
    return ClientCreate(
        last_name=last_name,
        first_name="Иван",
        middle_name="Иванович",
        birth_date=date(1990, 1, 1),
        center_ids=center_ids,
    )


def client_update(last_name: str, **extra) -> ClientUpdate:
    return ClientUpdate(last_name=last_name, first_name="Иван", middle_name="Иванович", birth_date=date(1990, 1, 1), **extra)


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.sent: list[tuple[list[str], str, str]] = []
        patcher = mock.patch.object(notifications, "send_email", side_effect=self._capture)
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.Session() as db:
            db.add(Center(id=1, code="center-a", name="Мед-Авто"))
            roles = {code: Role(code=code, name=code) for code in ("admin", "doctor")}
            db.add_all(roles.values())
            db.flush()
            db.add_all(
                [
                    User(
                        role_id=roles["admin"].id,
                        login="admin",
                        password_hash=hash_password("admin123"),
                        full_name="Евгений",
                        email="logdog3@yandex.ru",
                        is_active=True,
                    ),
                    User(
                        role_id=roles["admin"].id,
                        login="admin2",
                        password_hash=hash_password("admin234"),
                        full_name="Без почты",
                        email=None,
                        is_active=True,
                    ),
                    User(
                        role_id=roles["admin"].id,
                        login="retired",
                        password_hash=hash_password("retired1"),
                        full_name="Уволен",
                        email="old@example.com",
                        is_active=False,
                    ),
                    User(
                        role_id=roles["doctor"].id,
                        login="boris",
                        password_hash=hash_password("boris123"),
                        full_name="Борис",
                        email="boris@example.com",
                        is_active=True,
                        center_id=1,
                    ),
                ]
            )
            db.commit()

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _capture(self, recipients, subject, body) -> bool:
        self.sent.append((list(recipients), subject, body))
        return True

    def _user(self, db, login: str) -> User:
        return db.execute(select(User).where(User.login == login)).scalar_one()

    @staticmethod
    def _run(background: BackgroundTasks) -> None:
        """Выполняет отложенные письма так же, как их выполнит сервер после ответа."""
        for task in background.tasks:
            task.func(*task.args, **task.kwargs)

    def test_only_active_admins_with_an_email_receive_changes(self):
        with self.Session() as db:
            self.assertEqual(notifications.admin_notification_emails(db), ["logdog3@yandex.ru"])

    def test_a_change_is_sent_to_the_admin_email(self):
        with self.Session() as db:
            background = BackgroundTasks()
            notifications.notify_change(
                background, db, title="Изменен график работы", actor="Евгений", lines=["Сотрудник: Борис"]
            )
            self.assertEqual(len(background.tasks), 1)
            self._run(background)

        recipients, subject, body = self.sent[0]
        self.assertEqual(recipients, ["logdog3@yandex.ru"])
        self.assertEqual(subject, "Медцентр: Изменен график работы")
        self.assertIn("Кто изменил: Евгений", body)
        self.assertIn("Сотрудник: Борис", body)

    def test_no_admin_email_means_nothing_is_queued(self):
        with self.Session() as db:
            self._user(db, "admin").email = None
            db.commit()
            background = BackgroundTasks()
            notifications.notify_change(background, db, title="Изменен график работы", actor="Евгений", lines=[])

        self.assertEqual(background.tasks, [])

    def test_a_failed_send_is_logged_and_does_not_raise(self):
        with mock.patch.object(notifications, "send_email", side_effect=OSError("smtp недоступен")):
            notifications._deliver(["logdog3@yandex.ru"], "Медцентр: тест", "Текст")

    def test_nothing_is_sent_without_smtp_settings(self):
        with mock.patch.object(notifications.settings, "smtp_host", None):
            self.assertFalse(REAL_SEND_EMAIL(["logdog3@yandex.ru"], "Тема", "Текст"))

    def test_staff_email_is_trimmed_and_checked(self):
        self.assertEqual(StaffEmailUpdate(email="  logdog3@yandex.ru ").email, "logdog3@yandex.ru")
        self.assertIsNone(StaffEmailUpdate(email="   ").email)
        self.assertIsNone(StaffEmailUpdate(email=None).email)
        for bad in ("нет почты", "logdog3.yandex.ru", "a@b", "a b@yandex.ru", "a@b.", "@yandex.ru"):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                StaffEmailUpdate(email=bad)
        with self.assertRaises(ValidationError) as caught:
            StaffEmailUpdate(email="a@b")
        self.assertEqual(caught.exception.errors()[0]["msg"], "Укажите почту в формате name@example.com")

    def test_admin_changes_the_email_of_an_employee(self):
        with self.Session() as db:
            boris = self._user(db, "boris")
            updated = staff_routes.update_staff_email(
                user_id=boris.id,
                payload=StaffEmailUpdate(email="new@example.com"),
                _=self._user(db, "admin"),
                db=db,
            )
            self.assertEqual(updated.email, "new@example.com")
            with self.assertRaises(HTTPException) as caught:
                staff_routes.update_staff_email(
                    user_id=999_999, payload=StaffEmailUpdate(email="x@example.com"), _=self._user(db, "admin"), db=db
                )
            self.assertEqual(caught.exception.status_code, 404)

    def test_a_day_edit_is_reported_with_the_new_time(self):
        with self.Session() as db:
            boris = self._user(db, "boris")
            background = BackgroundTasks()
            schedule_routes.update_day(
                user_id=boris.id,
                work_date=date(2026, 11, 5),
                payload=WorkScheduleDayUpdate(kind="shift", start_time=time(9), end_time=time(20)),
                background_tasks=background,
                admin=self._user(db, "admin"),
                db=db,
            )
            self._run(background)

        _, subject, body = self.sent[0]
        self.assertEqual(subject, "Медцентр: Изменен график работы")
        self.assertIn("Сотрудник: Борис", body)
        self.assertIn("Дата: 05.11.2026", body)
        self.assertIn("Стало: смена 09:00-20:00", body)

    def test_a_new_employee_with_a_schedule_is_reported(self):
        with self.Session() as db:
            admin = self._user(db, "admin")
            background = BackgroundTasks()
            staff_routes.create_staff(
                payload=StaffUserCreate(
                    login="ivan",
                    password="pass1234",
                    full_name="Иван Сотрудников",
                    role_code="doctor",
                    center_ids=[1],
                    schedule=schedule(),
                ),
                background_tasks=background,
                current_user=admin,
                db=db,
            )
            self._run(background)

        _, subject, body = self.sent[0]
        self.assertEqual(subject, "Медцентр: Создан график работы")
        self.assertIn("Сотрудник: Иван Сотрудников", body)
        self.assertIn("График: 2/2, 09:00-20:00", body)

    def test_a_new_employee_without_a_schedule_reports_nothing(self):
        with self.Session() as db:
            background = BackgroundTasks()
            staff_routes.create_staff(
                payload=StaffUserCreate(
                    login="petr",
                    password="pass1234",
                    full_name="Петр",
                    role_code="doctor",
                    center_ids=[1],
                ),
                background_tasks=background,
                current_user=self._user(db, "admin"),
                db=db,
            )

        self.assertEqual(background.tasks, [])

    def test_a_schedule_time_change_shows_before_and_after(self):
        with self.Session() as db:
            boris = self._user(db, "boris")
            admin = self._user(db, "admin")
            background = BackgroundTasks()
            staff_routes.update_staff_schedule(
                user_id=boris.id,
                payload=StaffScheduleUpdate(schedule=schedule()),
                background_tasks=background,
                admin=admin,
                db=db,
            )
            self._run(background)

            again = BackgroundTasks()
            staff_routes.update_staff_schedule(
                user_id=boris.id,
                payload=StaffScheduleUpdate(schedule=schedule()),
                background_tasks=again,
                admin=admin,
                db=db,
            )

        _, subject, body = self.sent[0]
        self.assertEqual(subject, "Медцентр: Изменено время работы")
        self.assertIn("Было: без графика", body)
        self.assertIn("Стало: 2/2, 09:00-20:00", body)
        self.assertEqual(again.tasks, [])

    def test_a_client_name_change_is_reported_after_the_client_is_added(self):
        with self.Session() as db:
            admin = self._user(db, "admin")
            created = clients_routes.create_client(client_create("Петров", [1]), db=db, current_user=admin)
            background = BackgroundTasks()
            clients_routes.update_client(
                created.id,
                client_update("Иванов"),
                background_tasks=background,
                current_user=admin,
                db=db,
            )
            self._run(background)

            same_name = BackgroundTasks()
            clients_routes.update_client(
                created.id,
                client_update("Иванов", phone="+7 900 111-22-33"),
                background_tasks=same_name,
                current_user=admin,
                db=db,
            )

        _, subject, body = self.sent[0]
        self.assertEqual(subject, "Медцентр: Изменено ФИО клиента")
        self.assertIn("Было: Петров Иван Иванович", body)
        self.assertIn("Стало: Иванов Иван Иванович", body)
        self.assertEqual(same_name.tasks, [])


if __name__ == "__main__":
    unittest.main()
