from __future__ import annotations

from datetime import datetime, timezone
from email.message import EmailMessage
import logging
import smtplib
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import Role, User

logger = logging.getLogger(__name__)


def send_deletion_notification(subject: str, body: str) -> bool:
    if not (settings.deletion_notify_email and settings.smtp_host and settings.smtp_from):
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from
    message["To"] = settings.deletion_notify_email
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        smtp.starttls()
        if settings.smtp_user and settings.smtp_password:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)
    return True


def send_email(recipients: list[str], subject: str, body: str) -> bool:
    """Письмо на список адресов через SMTP из настроек. Без адреса или SMTP ничего не отправляет."""
    if not (recipients and settings.smtp_host and settings.smtp_from):
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from
    message["To"] = ", ".join(recipients)
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        smtp.starttls()
        if settings.smtp_user and settings.smtp_password:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)
    return True


def admin_notification_emails(db: Session) -> list[str]:
    """Почта активных админов: на нее уходят уведомления об изменениях графика и ФИО клиентов."""
    rows = db.execute(
        select(User.email)
        .join(Role, User.role_id == Role.id)
        .where(Role.code == "admin", User.is_active.is_(True), User.email.is_not(None))
        .order_by(User.id.asc())
    ).scalars().all()
    emails: list[str] = []
    for email in rows:
        normalized = (email or "").strip()
        if normalized and normalized not in emails:
            emails.append(normalized)
    return emails


def _local_label(moment: datetime) -> str:
    try:
        zone = ZoneInfo(settings.xml_exports_timezone)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("Europe/Moscow")
    return moment.astimezone(zone).strftime("%d.%m.%Y %H:%M")


def _deliver(recipients: list[str], subject: str, body: str) -> None:
    try:
        if not send_email(recipients, subject, body):
            logger.warning("Уведомление не отправлено: SMTP не настроен (%s)", subject)
    except Exception:
        # Изменение уже сохранено; ошибка почты не должна ронять запрос.
        logger.exception("Не удалось отправить уведомление: %s", subject)


def notify_change(
    background_tasks: BackgroundTasks,
    db: Session,
    *,
    title: str,
    actor: str,
    lines: list[str],
) -> None:
    """Ставит письмо админам в фоновую отправку. Без адресов админов ничего не делает."""
    recipients = admin_notification_emails(db)
    if not recipients:
        return
    body = "\n".join([f"Кто изменил: {actor}", f"Когда: {_local_label(datetime.now(timezone.utc))}", *lines])
    background_tasks.add_task(_deliver, recipients, f"Медцентр: {title}", body)


def build_deletion_email_body(
    *,
    entity_label: str,
    entity_id: int,
    deleted_by: str | None,
    deleted_at: str,
    details: dict[str, str | int | None],
) -> str:
    lines = [
        f"Удалена сущность: {entity_label}",
        f"ID: {entity_id}",
        f"Удалил: {deleted_by or 'неизвестный пользователь'}",
        f"Удалено: {deleted_at}",
    ]
    for key, value in details.items():
        lines.append(f"{key}: {value if value is not None else '-'}")
    return "\n".join(lines)
