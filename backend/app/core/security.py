import secrets
from functools import lru_cache
from hashlib import sha256

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# argon2id с параметрами из рекомендаций OWASP (19 МиБ памяти, 2 прохода).
# Память умеренная: при одновременных входах сервер не должен задыхаться.
_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)

ARGON2_PREFIX = "$argon2"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def _legacy_sha256(password: str) -> str:
    """Старый формат без соли. Такие хеши остаются в базе до первого успешного входа."""
    return sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash.startswith(ARGON2_PREFIX):
        return secrets.compare_digest(
            _legacy_sha256(password).encode("ascii"),
            password_hash.encode("utf-8"),
        )
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Нужно ли перехешировать пароль после успешного входа: старый SHA-256 или устаревшие параметры."""
    if not password_hash.startswith(ARGON2_PREFIX):
        return True
    return _hasher.check_needs_rehash(password_hash)


@lru_cache(maxsize=1)
def _placeholder_hash() -> str:
    return hash_password(secrets.token_urlsafe(16))


def spend_password_check_time(password: str) -> None:
    """Для неизвестного логина делает ту же проверку, что и для настоящего.

    Иначе argon2 отвечает заметно быстрее, и по времени ответа видно, какие логины существуют.
    """
    verify_password(password, _placeholder_hash())


def generate_session_epoch() -> str:
    """Метка сеансов пользователя.

    Входит в выданный токен. Пока метка не менялась, все ранее выданные токены
    остаются рабочими, поэтому вход на втором устройстве не выкидывает первое.
    Смена метки обесценивает все токены пользователя — на этом построена кнопка
    «Выйти у всех».
    """
    return secrets.token_hex(16)
