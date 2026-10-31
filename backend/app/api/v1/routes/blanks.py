from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.routes.auth import get_current_user, get_optional_current_user
from app.db.session import get_db
from app.models.blank_form import BlankBatch, BlankForm
from app.models.center import Center
from app.models.user import User
from app.schemas.blank_form import (
    BlankBatchCreate,
    BlankBatchPartRead,
    BlankBatchPartSplitRequest,
    BlankBatchRead,
    BlankClearRequest,
    BlankClearResult,
    BlankFormRead,
    BlankFormsPageRead,
    BlankFormSpoilRequest,
    BlankSeriesRead,
    BlankStatsItem,
    BlankStatsResponse,
    BlankTypeRead,
)
from app.services.blank_forms import (
    BlankNotFreeError,
    BlankPartsExistError,
    BlankRangeInvalidError,
    BlankRangeOverlapError,
    BlankServiceError,
    clear_center_blanks,
    create_auto_number_form,
    create_batch,
    enrich_form_for_read,
    get_form_by_printed_number,
    get_next_free_form,
    is_paper_certificate_series,
    list_batch_parts_with_counts,
    list_free_series,
    list_batches,
    list_blank_types,
    list_forms,
    list_forms_page,
    manual_pick_form,
    release_form,
    resolve_blank_type_for_series,
    split_batch_into_parts,
    spoil_form,
    stats as compute_stats,
)


router = APIRouter()

BLANK_CLEAR_ROLE_CODES = ("chairman",)


def _current_user_id(current_user: User | None) -> int:
    return current_user.id if current_user is not None else 1


def _check_center_access(current_user: User | None, center_id: int | None) -> None:
    if current_user is None or current_user.sees_all_centers:
        return
    if center_id not in {center.id for center in current_user.work_centers}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Бланки другого медцентра недоступны")


@router.get("/types", response_model=list[BlankTypeRead])
def get_blank_types(db: Session = Depends(get_db)) -> list[BlankTypeRead]:
    return [BlankTypeRead.model_validate(item) for item in list_blank_types(db)]


@router.get("/series", response_model=list[BlankSeriesRead])
def get_free_series(
    blank_type: str = Query(...),
    center_id: int | None = Query(default=None),
    strict_only: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[BlankSeriesRead]:
    items = list_free_series(db, blank_type=blank_type, center_id=center_id, strict_only=strict_only)
    return [BlankSeriesRead(**item) for item in items]


@router.get("/batches", response_model=list[BlankBatchRead])
def get_batches(
    blank_type: str | None = Query(default=None),
    center_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[BlankBatchRead]:
    items = list_batches(db, blank_type=blank_type, center_id=center_id)
    parts_by_batch = list_batch_parts_with_counts(db, [batch.id for batch, _ in items])
    result: list[BlankBatchRead] = []
    for batch, counts in items:
        payload = BlankBatchRead.model_validate(batch)
        payload.free_count = counts.get("free", 0)
        payload.issued_count = counts.get("issued", 0)
        payload.spoiled_count = counts.get("spoiled", 0)
        payload.cancelled_count = counts.get("cancelled", 0)
        payload.is_paper_certificate = is_paper_certificate_series(batch.series, batch.comment)
        payload.parts = [BlankBatchPartRead(**part) for part in parts_by_batch.get(batch.id, [])]
        result.append(payload)
    return result


@router.post("/batches", response_model=BlankBatchRead, status_code=status.HTTP_201_CREATED)
def create_batch_endpoint(
    payload: BlankBatchCreate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
) -> BlankBatchRead:
    _check_center_access(current_user, payload.center_id)
    try:
        batch = create_batch(
            db,
            blank_type=payload.blank_type,
            series=payload.series,
            number_from_input=payload.number_from,
            number_to_input=payload.number_to,
            received_at=payload.received_at,
            comment=payload.comment,
            center_id=payload.center_id,
            user_id=_current_user_id(current_user),
        )
    except BlankRangeOverlapError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except BlankRangeInvalidError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except BlankServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    db.commit()
    db.refresh(batch)
    response = BlankBatchRead.model_validate(batch)
    response.free_count = batch.quantity
    return response


@router.post("/batches/{batch_id}/parts", response_model=list[BlankBatchPartRead], status_code=status.HTTP_201_CREATED)
def split_batch_endpoint(
    batch_id: int,
    payload: BlankBatchPartSplitRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
) -> list[BlankBatchPartRead]:
    """Разбивает партию на пачки: каждый оператор берёт свою."""

    batch = db.get(BlankBatch, batch_id)
    if batch is not None:
        _check_center_access(current_user, batch.center_id)
    try:
        split_batch_into_parts(
            db,
            batch_id=batch_id,
            pack_size=payload.pack_size,
            ranges=[(part.number_from, part.number_to) for part in payload.parts] if payload.parts is not None else None,
            user_id=_current_user_id(current_user),
        )
    except BlankPartsExistError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except BlankRangeInvalidError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except BlankServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    db.commit()
    parts = list_batch_parts_with_counts(db, [batch_id]).get(batch_id, [])
    return [BlankBatchPartRead(**part) for part in parts]


@router.get("/forms", response_model=list[BlankFormRead])
def get_forms(
    blank_type: str | None = Query(default=None),
    batch_id: int | None = Query(default=None),
    blank_status: str | None = Query(default=None, alias="status"),
    center_id: int | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[BlankFormRead]:
    items = list_forms(
        db,
        blank_type=blank_type,
        batch_id=batch_id,
        status=blank_status,
        center_id=center_id,
        search=search,
        limit=limit,
    )
    return [BlankFormRead.model_validate(enrich_form_for_read(db, item)) for item in items]


@router.get("/forms/page", response_model=BlankFormsPageRead)
def get_forms_page(
    blank_type: str | None = Query(default=None),
    batch_id: int | None = None,
    blank_status: str | None = Query(default=None, alias="status"),
    center_id: int | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> BlankFormsPageRead:
    items, total = list_forms_page(
        db,
        blank_type=blank_type,
        batch_id=batch_id,
        status=blank_status,
        center_id=center_id,
        search=search,
        limit=limit,
        offset=offset,
    )
    return BlankFormsPageRead(
        items=[BlankFormRead.model_validate(enrich_form_for_read(db, item)) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/forms/next", response_model=BlankFormRead)
def get_next_form(
    blank_type: str = Query(...),
    center_id: int | None = Query(default=None),
    series: str | None = Query(default=None),
    auto_create: bool = Query(default=False),
    strict_only: bool = Query(default=False),
    batch_part_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
) -> BlankFormRead:
    blank_type = resolve_blank_type_for_series(blank_type, series)
    if auto_create and (strict_only or batch_part_id is not None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для строгого бланка автонумерация не применяется: номер берётся из заведённой партии",
        )
    if auto_create:
        _check_center_access(current_user, center_id)
        try:
            form = create_auto_number_form(
                db,
                blank_type=blank_type,
                center_id=center_id,
                series=series or "",
                user_id=_current_user_id(current_user),
            )
        except BlankRangeInvalidError as exc:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except BlankRangeOverlapError as exc:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except BlankServiceError as exc:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        db.commit()
        db.refresh(form)
        return BlankFormRead.model_validate(enrich_form_for_read(db, form))

    form = get_next_free_form(
        db,
        blank_type=blank_type,
        center_id=center_id,
        series=series,
        strict_only=strict_only,
        batch_part_id=batch_part_id,
    )
    if form is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Свободные бланки не найдены. Заведите диапазон номеров в разделе «Бланки»"
            if batch_part_id is None
            else "В этой пачке свободных бланков не осталось. Выберите другую пачку",
        )
    return BlankFormRead.model_validate(enrich_form_for_read(db, form))


@router.get("/forms/exact", response_model=BlankFormRead)
def get_exact_form(
    blank_type: str = Query(...),
    center_id: int | None = Query(default=None),
    series: str = Query(...),
    number: str = Query(...),
    strict_only: bool = Query(default=False),
    batch_part_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> BlankFormRead:
    blank_type = resolve_blank_type_for_series(blank_type, series)
    try:
        form = get_form_by_printed_number(
            db,
            blank_type=blank_type,
            center_id=center_id,
            series=series,
            number_input=number,
            strict_only=strict_only,
            batch_part_id=batch_part_id,
        )
    except BlankRangeInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if form is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Бланк с указанными серией и номером не найден",
        )
    return BlankFormRead.model_validate(enrich_form_for_read(db, form))


@router.post("/forms/{form_id}/manual-pick", response_model=BlankFormRead)
def manual_pick_endpoint(
    form_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
) -> BlankFormRead:
    """Фиксирует выбор номера, вписанного вручную, в истории."""

    candidate = db.get(BlankForm, form_id)
    if candidate is not None:
        _check_center_access(current_user, candidate.center_id)
    try:
        form = manual_pick_form(db, form_id=form_id, user_id=_current_user_id(current_user))
    except BlankNotFreeError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except BlankServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    db.commit()
    db.refresh(form)
    return BlankFormRead.model_validate(enrich_form_for_read(db, form))


@router.post("/forms/{form_id}/spoil", response_model=BlankFormRead)
def spoil_form_endpoint(
    form_id: int,
    payload: BlankFormSpoilRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
) -> BlankFormRead:
    candidate = db.get(BlankForm, form_id)
    if candidate is not None:
        _check_center_access(current_user, candidate.center_id)
    reason = payload.reason if payload is not None else None
    try:
        form = spoil_form(db, form_id=form_id, reason=reason, user_id=_current_user_id(current_user))
    except BlankServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    db.commit()
    db.refresh(form)
    return BlankFormRead.model_validate(enrich_form_for_read(db, form))


@router.post("/forms/{form_id}/release", response_model=BlankFormRead)
def release_form_endpoint(
    form_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
) -> BlankFormRead:
    candidate = db.get(BlankForm, form_id)
    if candidate is not None:
        _check_center_access(current_user, candidate.center_id)
    try:
        form = release_form(db, form_id=form_id, user_id=_current_user_id(current_user))
    except BlankServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    db.commit()
    db.refresh(form)
    return BlankFormRead.model_validate(enrich_form_for_read(db, form))


def require_blank_clear_access(current_user: User = Depends(get_current_user)) -> User:
    role_code = current_user.role.code if current_user.role is not None else ""
    if role_code not in BLANK_CLEAR_ROLE_CODES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Очищать бланки может только председатель",
        )
    return current_user


@router.post("/clear", response_model=BlankClearResult)
def clear_blanks_endpoint(
    payload: BlankClearRequest,
    current_user: User = Depends(require_blank_clear_access),
    db: Session = Depends(get_db),
) -> BlankClearResult:
    if db.get(Center, payload.center_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Медцентр не найден")
    result = clear_center_blanks(db, center_id=payload.center_id, user_id=current_user.id)
    db.commit()
    return BlankClearResult(center_id=payload.center_id, **result)


@router.get("/stats", response_model=BlankStatsResponse)
def get_stats(
    center_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> BlankStatsResponse:
    return BlankStatsResponse(
        items=[BlankStatsItem(**row) for row in compute_stats(db, center_id=center_id)]
    )
