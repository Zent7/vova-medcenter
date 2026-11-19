from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.v1.routes.auth import get_current_user
from app.api.v1.routes.documents import _resolve_generated_file, issue_print_ticket
from app.db.session import get_db
from app.models.print_queue import PrintAgent, PrintJob
from app.models.user import User
from app.schemas.print_queue import (
    AgentClaimResponse,
    AgentHeartbeatResponse,
    AgentJob,
    AgentResultRequest,
    PrintJobCreate,
    PrintJobRead,
)
from app.services.print_queue import (
    PrintQueueError,
    authenticate_agent,
    cancel_job,
    claim_next_job,
    create_job,
    document_center_id,
    fail_claimed_job,
    find_printable_document,
    get_job,
    report_job_result,
    touch_agent,
    utc_now,
)

# Для сотрудников: поставить документ в очередь, посмотреть и отменить свое задание.
# Подключается в protected_router, то есть требует входа.
router = APIRouter()

# Для печатных агентов: им нужен токен агента, а не вход сотрудника. Поэтому маршруты
# подключаются мимо protected_router, и test_api_requires_login перечисляет их отдельно.
agent_router = APIRouter()


def _http_error(exc: PrintQueueError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _check_center_access(user: User, center_id: int | None) -> None:
    if center_id is None or user.sees_all_centers:
        return
    if center_id not in {center.id for center in user.work_centers}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Документ другого медцентра")


def _check_job_access(user: User, job: PrintJob) -> None:
    if job.requested_by_user_id == user.id or user.sees_all_centers:
        return
    if job.center_id is not None and job.center_id in {center.id for center in user.work_centers}:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Задание другого сотрудника")


def get_print_agent(
    x_print_agent_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> PrintAgent:
    try:
        return authenticate_agent(db, x_print_agent_token)
    except PrintQueueError as exc:
        raise _http_error(exc) from exc


@router.post("", response_model=PrintJobRead, status_code=status.HTTP_201_CREATED)
def create_print_job(
    payload: PrintJobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PrintJobRead:
    document = find_printable_document(db, payload.file_name)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Документ не найден или отменен")
    center_id = document_center_id(db, document)
    _check_center_access(current_user, center_id)
    try:
        job = create_job(
            db,
            document=document,
            center_id=center_id,
            copies=payload.copies,
            user_id=current_user.id,
            now=utc_now(),
        )
    except PrintQueueError as exc:
        raise _http_error(exc) from exc
    return PrintJobRead.model_validate(job)


@router.get("/{job_id}", response_model=PrintJobRead)
def get_print_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PrintJobRead:
    job = get_job(db, job_id, utc_now())
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задание печати не найдено")
    _check_job_access(current_user, job)
    return PrintJobRead.model_validate(job)


@router.post("/{job_id}/cancel", response_model=PrintJobRead)
def cancel_print_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PrintJobRead:
    job = get_job(db, job_id, utc_now())
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задание печати не найдено")
    _check_job_access(current_user, job)
    try:
        job = cancel_job(db, job, utc_now())
    except PrintQueueError as exc:
        raise _http_error(exc) from exc
    return PrintJobRead.model_validate(job)


@agent_router.post("/heartbeat", response_model=AgentHeartbeatResponse)
def agent_heartbeat(
    agent: PrintAgent = Depends(get_print_agent),
    db: Session = Depends(get_db),
) -> AgentHeartbeatResponse:
    now = utc_now()
    touch_agent(db, agent, now)
    return AgentHeartbeatResponse(
        agent_id=agent.id,
        name=agent.name,
        center_id=agent.center_id,
        printer_name=agent.printer_name,
        server_time=now,
    )


@agent_router.post("/jobs/claim", response_model=AgentClaimResponse)
def agent_claim_job(
    request: Request,
    agent: PrintAgent = Depends(get_print_agent),
    db: Session = Depends(get_db),
) -> AgentClaimResponse:
    now = utc_now()
    job = claim_next_job(db, agent, now)
    if job is None:
        return AgentClaimResponse(job=None)
    file_path = _resolve_generated_file(job.file_name)
    if file_path is None:
        fail_claimed_job(db, job, "Файл документа не найден", now)
        return AgentClaimResponse(job=None)
    ticket = issue_print_ticket(file_path, request)
    return AgentClaimResponse(
        job=AgentJob(
            id=job.id,
            file_name=job.file_name,
            copies=job.copies,
            printer_name=agent.printer_name,
            file_url=ticket.file_url,
        )
    )


@agent_router.post("/jobs/{job_id}/result", response_model=PrintJobRead)
def agent_report_result(
    job_id: int,
    payload: AgentResultRequest,
    agent: PrintAgent = Depends(get_print_agent),
    db: Session = Depends(get_db),
) -> PrintJobRead:
    try:
        job = report_job_result(db, agent, job_id, ok=payload.ok, error=payload.error, now=utc_now())
    except PrintQueueError as exc:
        raise _http_error(exc) from exc
    return PrintJobRead.model_validate(job)
