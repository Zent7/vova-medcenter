"""Очередь тихой печати.

Сотрудник ставит готовый документ в очередь своего центра. Печатный агент на рабочем месте
сам опрашивает сервер, забирает задание, печатает его и сообщает результат. Агенту нужен
только исходящий доступ к серверу, поэтому браузер никогда не обращается к localhost.

Задание не переотправляется само: если агент пропал после выдачи, задание помечается ошибкой,
чтобы документ не напечатался дважды.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models.encounter import Encounter
from app.models.generated_document import GeneratedDocument
from app.models.print_queue import (
    PRINT_JOB_CANCELLED,
    PRINT_JOB_CLAIMED,
    PRINT_JOB_DONE,
    PRINT_JOB_FAILED,
    PRINT_JOB_QUEUED,
    PrintAgent,
    PrintJob,
)

# Агент считается в сети, если опрашивал сервер не позже этого срока.
AGENT_ONLINE_WINDOW = timedelta(seconds=60)
# Задание, которое агент взял и не отчитался, через это время помечается ошибкой.
CLAIM_TIMEOUT = timedelta(minutes=5)
MAX_COPIES = 20
MAX_ERROR_LENGTH = 500
_CLAIM_ATTEMPTS = 5


class PrintQueueError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    # SQLite отдает даты без часового пояса, но пишем мы всегда в UTC.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def hash_agent_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_agent(db: Session, *, name: str, center_id: int | None, printer_name: str | None) -> tuple[PrintAgent, str]:
    """Заводит агент и возвращает его токен. Токен показывается один раз, в базе только хеш."""
    token = secrets.token_urlsafe(32)
    agent = PrintAgent(
        name=name.strip(),
        center_id=center_id,
        printer_name=(printer_name or "").strip() or None,
        token_hash=hash_agent_token(token),
        created_at=utc_now(),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent, token


def revoke_agent(db: Session, agent_id: int) -> PrintAgent:
    agent = db.get(PrintAgent, agent_id)
    if agent is None:
        raise PrintQueueError(404, "Печатный агент не найден")
    if agent.revoked_at is None:
        agent.revoked_at = utc_now()
        db.commit()
    return agent


def authenticate_agent(db: Session, token: str | None) -> PrintAgent:
    if not token:
        raise PrintQueueError(401, "Нет токена печатного агента")
    agent = db.execute(
        select(PrintAgent).where(
            PrintAgent.token_hash == hash_agent_token(token),
            PrintAgent.revoked_at.is_(None),
        )
    ).scalar_one_or_none()
    if agent is None:
        raise PrintQueueError(401, "Токен печатного агента не подходит или отозван")
    return agent


def agent_is_online(agent: PrintAgent, now: datetime) -> bool:
    return (
        agent.revoked_at is None
        and agent.last_seen_at is not None
        and now - as_utc(agent.last_seen_at) <= AGENT_ONLINE_WINDOW
    )


def touch_agent(db: Session, agent: PrintAgent, now: datetime) -> None:
    agent.last_seen_at = now
    db.commit()


def _agents_for_center(db: Session, center_id: int | None) -> list[PrintAgent]:
    query = select(PrintAgent).where(PrintAgent.revoked_at.is_(None))
    if center_id is not None:
        query = query.where(or_(PrintAgent.center_id.is_(None), PrintAgent.center_id == center_id))
    return list(db.execute(query).scalars())


def has_online_agent(db: Session, center_id: int | None, now: datetime) -> bool:
    return any(agent_is_online(agent, now) for agent in _agents_for_center(db, center_id))


def expire_stale_claims(db: Session, now: datetime) -> None:
    db.execute(
        update(PrintJob)
        .where(PrintJob.status == PRINT_JOB_CLAIMED, PrintJob.claimed_at < now - CLAIM_TIMEOUT)
        .values(status=PRINT_JOB_FAILED, error="Агент не ответил вовремя", finished_at=now)
    )
    db.commit()


def find_printable_document(db: Session, file_name: str) -> GeneratedDocument | None:
    return db.execute(
        select(GeneratedDocument)
        .where(
            GeneratedDocument.file_name == file_name,
            GeneratedDocument.cancelled_at.is_(None),
            GeneratedDocument.file_deleted_at.is_(None),
        )
        .order_by(GeneratedDocument.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def document_center_id(db: Session, document: GeneratedDocument) -> int | None:
    if document.encounter_id is None:
        return None
    encounter = db.get(Encounter, document.encounter_id)
    return encounter.center_id if encounter is not None else None


def create_job(
    db: Session,
    *,
    document: GeneratedDocument,
    center_id: int | None,
    copies: int,
    user_id: int | None,
    now: datetime,
) -> PrintJob:
    """Ставит документ в очередь. Если агента нет в сети, задание не создается: документ откроется вручную."""
    if not 1 <= copies <= MAX_COPIES:
        raise PrintQueueError(422, f"Количество копий от 1 до {MAX_COPIES}")
    expire_stale_claims(db, now)
    if not has_online_agent(db, center_id, now):
        raise PrintQueueError(409, "Печатный агент не в сети")
    job = PrintJob(
        generated_document_id=document.id,
        file_name=document.file_name,
        center_id=center_id,
        copies=copies,
        status=PRINT_JOB_QUEUED,
        requested_by_user_id=user_id,
        created_at=now,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def claim_next_job(db: Session, agent: PrintAgent, now: datetime) -> PrintJob | None:
    """Отдает агенту самое раннее задание его центра. Двойная выдача исключена условным UPDATE."""
    touch_agent(db, agent, now)
    expire_stale_claims(db, now)
    conditions = [PrintJob.status == PRINT_JOB_QUEUED]
    if agent.center_id is not None:
        conditions.append(or_(PrintJob.center_id.is_(None), PrintJob.center_id == agent.center_id))
    for _ in range(_CLAIM_ATTEMPTS):
        job_id = db.execute(select(PrintJob.id).where(*conditions).order_by(PrintJob.id).limit(1)).scalar_one_or_none()
        if job_id is None:
            return None
        claimed = db.execute(
            update(PrintJob)
            .where(PrintJob.id == job_id, PrintJob.status == PRINT_JOB_QUEUED)
            .values(status=PRINT_JOB_CLAIMED, agent_id=agent.id, claimed_at=now)
        ).rowcount
        if claimed == 1:
            db.commit()
            return db.get(PrintJob, job_id)
        db.rollback()
    return None


def fail_claimed_job(db: Session, job: PrintJob, error: str, now: datetime) -> None:
    job.status = PRINT_JOB_FAILED
    job.error = error[:MAX_ERROR_LENGTH]
    job.finished_at = now
    db.commit()


def report_job_result(
    db: Session,
    agent: PrintAgent,
    job_id: int,
    *,
    ok: bool,
    error: str | None,
    now: datetime,
) -> PrintJob:
    job = db.get(PrintJob, job_id)
    if job is None or job.agent_id != agent.id:
        raise PrintQueueError(404, "Задание печати не найдено")
    touch_agent(db, agent, now)
    if job.status in (PRINT_JOB_DONE, PRINT_JOB_FAILED):
        # Повторный отчет того же агента (например, после обрыва сети) ничего не меняет.
        return job
    if job.status != PRINT_JOB_CLAIMED:
        raise PrintQueueError(409, "Задание уже не в работе")
    job.status = PRINT_JOB_DONE if ok else PRINT_JOB_FAILED
    job.error = None if ok else ((error or "").strip()[:MAX_ERROR_LENGTH] or "Печать не удалась")
    job.finished_at = now
    db.commit()
    return job


def get_job(db: Session, job_id: int, now: datetime) -> PrintJob | None:
    expire_stale_claims(db, now)
    return db.get(PrintJob, job_id)


def cancel_job(db: Session, job: PrintJob, now: datetime) -> PrintJob:
    """Отменяет задание, пока агент его не взял. Условный UPDATE не дает отменить уже взятое."""
    if job.status == PRINT_JOB_CANCELLED:
        return job
    cancelled = db.execute(
        update(PrintJob)
        .where(PrintJob.id == job.id, PrintJob.status == PRINT_JOB_QUEUED)
        .values(status=PRINT_JOB_CANCELLED, finished_at=now)
    ).rowcount
    db.commit()
    db.refresh(job)
    if cancelled != 1:
        raise PrintQueueError(409, "Агент уже взял задание, отменить его нельзя")
    return job
