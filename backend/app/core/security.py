import secrets
from hashlib import sha256


def hash_password(password: str) -> str:
    return sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


def generate_session_epoch() -> str:
    """Метка сеансов пользователя.

    Входит в выданный токен. Пока метка не менялась, все ранее выданные токены
    остаются рабочими, поэтому вход на втором устройстве не выкидывает первое.
    Смена метки обесценивает все токены пользователя — на этом построена кнопка
    «Выйти у всех».
    """
    return secrets.token_hex(16)
