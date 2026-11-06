from hashlib import sha256
from pathlib import Path
import sys
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes import auth as auth_routes  # noqa: E402
from app.core.security import hash_password, needs_rehash, verify_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.user import Role, User  # noqa: E402
from app.schemas.auth import LoginRequest  # noqa: E402


def legacy_hash(password: str) -> str:
    return sha256(password.encode("utf-8")).hexdigest()


class PasswordHashingTests(unittest.TestCase):
    def test_new_hash_is_argon2id_and_verifies(self):
        stored = hash_password("клиника-2026")
        self.assertTrue(stored.startswith("$argon2id$"))
        self.assertTrue(verify_password("клиника-2026", stored))
        self.assertFalse(verify_password("другой", stored))
        self.assertFalse(needs_rehash(stored))

    def test_same_password_gets_different_salts(self):
        self.assertNotEqual(hash_password("admin123"), hash_password("admin123"))

    def test_legacy_sha256_hash_still_verifies_and_needs_rehash(self):
        stored = legacy_hash("doctor123")
        self.assertTrue(verify_password("doctor123", stored))
        self.assertFalse(verify_password("doctor124", stored))
        self.assertTrue(needs_rehash(stored))

    def test_malformed_hashes_are_rejected_without_crashing(self):
        self.assertFalse(verify_password("x", "$argon2id$broken"))
        self.assertFalse(verify_password("x", "test"))
        self.assertFalse(verify_password("x", ""))


class LoginUpgradesLegacyHashTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.original_session_local = auth_routes.SessionLocal
        auth_routes.SessionLocal = self.Session

        with self.Session() as db:
            role = Role(code="doctor", name="doctor")
            db.add(role)
            db.flush()
            db.add_all(
                [
                    User(
                        role_id=role.id,
                        login="legacy",
                        password_hash=legacy_hash("legacy123"),
                        full_name="Старый хеш",
                        is_active=True,
                    ),
                    User(
                        role_id=role.id,
                        login="fresh",
                        password_hash=hash_password("fresh123"),
                        full_name="Новый хеш",
                        is_active=True,
                    ),
                ]
            )
            db.commit()

    def tearDown(self):
        auth_routes.SessionLocal = self.original_session_local
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _stored_hash(self, login: str) -> str:
        with self.Session() as db:
            return db.execute(select(User.password_hash).where(User.login == login)).scalar_one()

    def test_successful_login_rewrites_legacy_hash_once(self):
        response = auth_routes.login(LoginRequest(login="legacy", password="legacy123"))
        self.assertTrue(response.access_token)

        upgraded = self._stored_hash("legacy")
        self.assertTrue(upgraded.startswith("$argon2id$"))
        self.assertTrue(verify_password("legacy123", upgraded))

        auth_routes.login(LoginRequest(login="legacy", password="legacy123"))
        self.assertEqual(self._stored_hash("legacy"), upgraded)

    def test_wrong_password_keeps_legacy_hash(self):
        with self.assertRaises(HTTPException) as raised:
            auth_routes.login(LoginRequest(login="legacy", password="не тот"))
        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(self._stored_hash("legacy"), legacy_hash("legacy123"))

    def test_unknown_login_is_rejected_with_the_same_message(self):
        with self.assertRaises(HTTPException) as raised:
            auth_routes.login(LoginRequest(login="nobody", password="whatever"))
        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(raised.exception.detail, "Неверный логин или пароль")

    def test_login_with_argon2_hash_does_not_rewrite_it(self):
        before = self._stored_hash("fresh")
        auth_routes.login(LoginRequest(login="fresh", password="fresh123"))
        self.assertEqual(self._stored_hash("fresh"), before)


if __name__ == "__main__":
    unittest.main()
