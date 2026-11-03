"""Учетную запись, по которой остались записи в программе, нельзя стереть.

На нее ссылаются клиенты, документы, бланки и журнал аудита, и стертая учетная запись
оборвала бы историю работы. Такую учетную запись отключают: она остается в списке со
статусом «Отключен» и больше не может войти. Учетную запись без записей удаляют.
"""

from pathlib import Path
import sys
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes import auth as auth_routes  # noqa: E402
from app.api.v1.routes import staff as staff_routes  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.user import Role, User  # noqa: E402
from app.schemas.auth import LoginRequest  # noqa: E402
from app.services.audit import write_audit_log  # noqa: E402


class StaffDeleteKeepsRecordsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(dbapi_connection, _record):
            # PostgreSQL проверяет внешние ключи всегда, SQLite — только когда их включили.
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.original_session_local = auth_routes.SessionLocal
        auth_routes.SessionLocal = self.Session

        with self.Session() as db:
            admin_role = Role(code="admin", name="Админ")
            operator_role = Role(code="operator", name="Оператор")
            db.add_all([admin_role, operator_role])
            db.flush()
            db.add_all(
                [
                    User(
                        role_id=admin_role.id,
                        login="admin",
                        password_hash=hash_password("admin123"),
                        full_name="Админ",
                    ),
                    User(
                        role_id=operator_role.id,
                        login="clean",
                        password_hash=hash_password("clean123"),
                        full_name="Без записей",
                    ),
                    User(
                        role_id=operator_role.id,
                        login="worked",
                        password_hash=hash_password("worked123"),
                        full_name="С записями",
                    ),
                ]
            )
            db.commit()

    def tearDown(self):
        auth_routes.SessionLocal = self.original_session_local
        # База в памяти: с включенными внешними ключами drop_all не справляется с порядком таблиц.
        self.engine.dispose()

    def _give_records(self, db, user):
        # «Выйти у всех» пишет журнал аудита с id сотрудника: это уже запись в программе.
        write_audit_log(db, entity_type="user_session", entity_id=user.id, action="logout_all", user_id=user.id)
        db.commit()

    def test_account_without_records_is_deleted(self):
        with self.Session() as db:
            admin = db.execute(select(User).where(User.login == "admin")).scalar_one()
            clean = db.execute(select(User).where(User.login == "clean")).scalar_one()

            result = staff_routes.delete_staff_user(user_id=clean.id, current_user=admin, db=db)

            self.assertTrue(result.deleted)
            self.assertIsNone(db.execute(select(User).where(User.login == "clean")).scalar_one_or_none())

    def test_account_with_records_is_deactivated_not_deleted(self):
        with self.Session() as db:
            admin = db.execute(select(User).where(User.login == "admin")).scalar_one()
            worked = db.execute(select(User).where(User.login == "worked")).scalar_one()
            self._give_records(db, worked)
            worked_id = worked.id

            result = staff_routes.delete_staff_user(user_id=worked_id, current_user=admin, db=db)

            self.assertFalse(result.deleted)
            kept = db.get(User, worked_id)
            self.assertIsNotNone(kept)
            self.assertFalse(kept.is_active)

    def test_deactivated_account_cannot_log_in(self):
        with self.Session() as db:
            admin = db.execute(select(User).where(User.login == "admin")).scalar_one()
            worked = db.execute(select(User).where(User.login == "worked")).scalar_one()
            self._give_records(db, worked)
            staff_routes.delete_staff_user(user_id=worked.id, current_user=admin, db=db)

        with self.assertRaises(HTTPException) as raised:
            auth_routes.login(LoginRequest(login="worked", password="worked123"))
        self.assertEqual(raised.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
