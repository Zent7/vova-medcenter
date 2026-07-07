from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.service import Service, ServiceDoctorRole
from app.schemas.service import ServiceRead, ServiceUpdate

router = APIRouter()

HIDDEN_SERVICE_LEGACY_IDS = (39,)

OPERATOR_SERVICE_PRIORITY = (
    8,   # Медицинская комиссия
    29,  # Медицинская комиссия, базовые категории
    18,  # ЛМК
    42,  # ЛМК справка
    19,  # Продление ЛМК
    7,   # 071У
    37,  # Медкомиссия для управления маломерными судами
    9,   # Справка 002 ЧОД (для охраны)
    12,  # Справка формы 086у
    2,   # Справка формы 001 ГСУ
    11,  # Справка для работы с гостайной формы 989Н
    4,   # Справка ГТО 1144
    5,   # спорт
    3,   # Справка для посещения бассейна
    27,  # ЭКГ
    30,  # 095
    24,  # Санаторно-курортная карта 072У
    31,  # Справка для получения путевки 070У
    10,  # Справка для выезжающих за границу 082у
    32,  # капельница
    38,  # Морская медицинская комиссия
    40,  # Справка 342н
    43,  # СЭМТ-196
)


@router.get("", response_model=list[ServiceRead])
def list_services(db: Session = Depends(get_db)) -> list[ServiceRead]:
    priority_order = case(
        *[
            (Service.legacy_source_id == legacy_id, index)
            for index, legacy_id in enumerate(OPERATOR_SERVICE_PRIORITY, start=1)
        ],
        else_=1000,
    )
    services = db.execute(
        select(Service)
        .where(
            Service.is_active.is_(True),
            or_(
                Service.legacy_source_id.is_(None),
                Service.legacy_source_id.not_in(HIDDEN_SERVICE_LEGACY_IDS),
            ),
        )
        .order_by(priority_order.asc(), Service.category_id.asc(), Service.legacy_source_id.asc(), Service.name.asc())
    ).scalars().all()
    service_ids = [item.id for item in services]
    role_rows = db.execute(
        select(ServiceDoctorRole.service_id, ServiceDoctorRole.doctor_role_id).where(ServiceDoctorRole.service_id.in_(service_ids))
    ).all() if service_ids else []
    roles_by_service: dict[int, list[int]] = {}
    for service_id, doctor_role_id in role_rows:
        roles_by_service.setdefault(service_id, []).append(doctor_role_id)

    result = []
    for item in services:
        payload = ServiceRead.model_validate(item)
        payload.doctor_role_ids = roles_by_service.get(item.id, [])
        result.append(payload)
    return result


@router.put("/{service_id}", response_model=ServiceRead)
def update_service(service_id: int, payload: ServiceUpdate, db: Session = Depends(get_db)) -> ServiceRead:
    service = db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Услуга не найдена")

    data = payload.model_dump(exclude_unset=True)
    doctor_role_ids = data.pop("doctor_role_ids", None)

    for field, value in data.items():
        setattr(service, field, value)

    if doctor_role_ids is not None:
        db.execute(ServiceDoctorRole.__table__.delete().where(ServiceDoctorRole.service_id == service.id))
        for doctor_role_id in doctor_role_ids:
            db.add(ServiceDoctorRole(service_id=service.id, doctor_role_id=doctor_role_id))

    db.commit()
    db.refresh(service)

    result = ServiceRead.model_validate(service)
    result.doctor_role_ids = doctor_role_ids if doctor_role_ids is not None else [
        row[0]
        for row in db.execute(
            select(ServiceDoctorRole.doctor_role_id).where(ServiceDoctorRole.service_id == service.id)
        ).all()
    ]
    return result
