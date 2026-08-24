from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.blank_form import (
    BlankBatchCreate,
    BlankBatchRead,
    BlankFormRead,
    BlankFormsPageRead,
    BlankFormSpoilRequest,
    BlankSeriesRead,
    BlankStatsItem,
    BlankStatsResponse,
    BlankTypeRead,
)
from app.services.blank_forms import (
    BlankRangeInvalidError,
    BlankRangeOverlapError,
    BlankServiceError,
    create_auto_number_form,
    create_batch,
    enrich_form_for_read,
    get_form_by_printed_number,
    get_next_free_form,
    list_free_series,
    list_batches,
    list_blank_types,
    list_forms,
    list_forms_page,
    release_form,
    resolve_blank_type_for_series,
    spoil_form,
    stats as compute_stats,
)


router = APIRouter()


def _current_user_id() -> int:
    """Заглушка под будущую авторизацию.

    В проекте сейчас нет JWT-зависимости, документация уже использует user_id=1
    (см. routes/doctor_exams.py), поэтому здесь следуем тому же подходу.
    """

    return 1


@router.get("/types", response_model=list[BlankTypeRead])
def get_blank_types(db: Session = Depends(get_db)) -> list[BlankTypeRead]:
    return [BlankTypeRead.model_validate(item) for item in list_blank_types(db)]


@router.get("/series", response_model=list[BlankSeriesRead])
def get_free_series(
    blank_type: str = Query(...),
    center_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[BlankSeriesRead]:
    items = list_free_series(db, blank_type=blank_type, center_id=center_id)
    return [BlankSeriesRead(**item) for item in items]


@router.get("/batches", response_model=list[BlankBatchRead])
def get_batches(
    blank_type: str | None = Query(default=None),
    center_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[BlankBatchRead]:
    items = list_batches(db, blank_type=blank_type, center_id=center_id)
    result: list[BlankBatchRead] = []
    for batch, counts in items:
        payload = BlankBatchRead.model_validate(batch)
        payload.free_count = counts.get("free", 0)
        payload.issued_count = counts.get("issued", 0)
        payload.spoiled_count = counts.get("spoiled", 0)
        payload.cancelled_count = counts.get("cancelled", 0)
        result.append(payload)
    return result


@router.post("/batches", response_model=BlankBatchRead, status_code=status.HTTP_201_CREATED)
def create_batch_endpoint(
    payload: BlankBatchCreate,
    db: Session = Depends(get_db),
) -> BlankBatchRead:
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
            user_id=_current_user_id(),
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
    db: Session = Depends(get_db),
) -> BlankFormRead:
    blank_type = resolve_blank_type_for_series(blank_type, series)
    if auto_create:
        try:
            form = create_auto_number_form(
                db,
                blank_type=blank_type,
                center_id=center_id,
                series=series or "",
                user_id=_current_user_id(),
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

    form = get_next_free_form(db, blank_type=blank_type, center_id=center_id, series=series)
    if form is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Свободные бланки не найдены. Заведите диапазон номеров в разделе «Бланки»",
        )
    return BlankFormRead.model_validate(enrich_form_for_read(db, form))


@router.get("/forms/exact", response_model=BlankFormRead)
def get_exact_form(
    blank_type: str = Query(...),
    center_id: int | None = Query(default=None),
    series: str = Query(...),
    number: str = Query(...),
    db: Session = Depends(get_db),
) -> BlankFormRead:
    try:
        form = get_form_by_printed_number(
            db,
            blank_type=blank_type,
            center_id=center_id,
            series=series,
            number_input=number,
        )
    except BlankRangeInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if form is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Бланк с указанными серией и номером не найден",
        )
    return BlankFormRead.model_validate(enrich_form_for_read(db, form))


@router.post("/forms/{form_id}/spoil", response_model=BlankFormRead)
def spoil_form_endpoint(
    form_id: int,
    payload: BlankFormSpoilRequest | None = None,
    db: Session = Depends(get_db),
) -> BlankFormRead:
    reason = payload.reason if payload is not None else None
    try:
        form = spoil_form(db, form_id=form_id, reason=reason, user_id=_current_user_id())
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
) -> BlankFormRead:
    try:
        form = release_form(db, form_id=form_id, user_id=_current_user_id())
    except BlankServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    db.commit()
    db.refresh(form)
    return BlankFormRead.model_validate(enrich_form_for_read(db, form))


@router.get("/stats", response_model=BlankStatsResponse)
def get_stats(
    center_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> BlankStatsResponse:
    return BlankStatsResponse(
        items=[BlankStatsItem(**row) for row in compute_stats(db, center_id=center_id)]
    )
