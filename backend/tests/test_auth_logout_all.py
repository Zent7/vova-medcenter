from pathlib import Path
import sys
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes import auth as auth_routes  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.user import Role, User  # noqa: E402
from app.schemas.auth import LoginRequest  # noqa: E402


class LogoutAllSessionsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.original_session_local = auth_routes.SessionLocal
        auth_routes.SessionLocal = self.Session

        with self.Session() as db:
            roles = {
                code: Role(code=code, name=code)
                for code in ("chairman", "admin", "doctor")
            }
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
                for code in ("chairman", "admin", "doctor")
            )
            db.commit()

    def tearDown(self):
        auth_routes.SessionLocal = self.original_session_local
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _login(self, login: str) -> str:
        response = auth_routes.login(LoginRequest(login=login, password=f"{login}123"))
        return response.access_token

    def _user(self, db, login: str) -> User:
        return db.execute(select(User).where(User.login == login)).scalar_one()

    def test_issued_token_carries_session_epoch_and_authenticates(self):
        token = self._login("doctor")
        with self.Session() as db:
            doctor = self._user(db, "doctor")
            self.assertEqual(token, f"demo-token-{doctor.id}.{doctor.session_epoch}")
            authenticated = auth_routes.get_current_user(authorization=f"Bearer {token}", db=db)
            self.assertEqual(authenticated.id, doctor.id)

    def test_repeated_login_keeps_the_previous_token_working(self):
        first_token = self._login("doctor")
        second_token = self._login("doctor")
        self.assertEqual(first_token, second_token)
        with self.Session() as db:
            self.assertIsNotNone(auth_routes.get_current_user(authorization=f"Bearer {first_token}", db=db))

    def test_logout_all_ends_every_session_including_the_caller(self):
        doctor_token = self._login("doctor")
        chairman_token = self._login("chairman")

        with self.Session() as db:
            chairman = self._user(db, "chairman")
            result = auth_routes.logout_all_sessions(current_user=chairman, db=db)
            self.assertEqual(result.ended_sessions, 3)

        with self.Session() as db:
            for token in (doctor_token, chairman_token):
                with self.assertRaises(HTTPException) as raised:
                    auth_routes.get_current_user(authorization=f"Bearer {token}", db=db)
                self.assertEqual(raised.exception.status_code, 401)
                self.assertEqual(raised.exception.detail, auth_routes.SESSION_ENDED_DETAIL)

    def test_logout_all_lets_everyone_log_in_again(self):
        old_token = self._login("doctor")
        with self.Session() as db:
            auth_routes.logout_all_sessions(current_user=self._user(db, "chairman"), db=db)

        new_token = self._login("doctor")
        self.assertNotEqual(new_token, old_token)
        with self.Session() as db:
            self.assertIsNotNone(auth_routes.get_current_user(authorization=f"Bearer {new_token}", db=db))

    def test_logout_all_writes_an_audit_record(self):
        with self.Session() as db:
            auth_routes.logout_all_sessions(current_user=self._user(db, "admin"), db=db)

        with self.Session() as db:
            log = db.execute(select(AuditLog).where(AuditLog.action == "logout_all")).scalar_one()
            self.assertEqual(log.entity_type, "user_session")
            self.assertEqual(log.payload_json, {"ended_sessions": 3})

    def test_token_without_session_epoch_is_rejected(self):
        with self.Session() as db:
            doctor = self._user(db, "doctor")
            with self.assertRaises(HTTPException) as raised:
                auth_routes.get_current_user(authorization=f"Bearer demo-token-{doctor.id}", db=db)
            self.assertEqual(raised.exception.status_code, 401)
            self.assertEqual(raised.exception.detail, auth_routes.SESSION_ENDED_DETAIL)

    def test_only_chairman_and_admin_may_end_all_sessions(self):
        with self.Session() as db:
            for login in ("chairman", "admin"):
                self.assertIsNotNone(auth_routes.require_session_manager(current_user=self._user(db, login)))

            with self.assertRaises(HTTPException) as raised:
                auth_routes.require_session_manager(current_user=self._user(db, "doctor"))
            self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
