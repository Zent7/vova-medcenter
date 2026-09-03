"""Справочник врачей медцентра: кто занимает специальность в этом центре.

Специальности общие для всех медцентров, а ФИО у каждого центра своё. Раньше имя
лежало в `doctor_roles.full_name` одной строкой на всю базу, поэтому второй центр
не мог завести своих врачей, не переписав их первому.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.center_doctor_name import CenterDoctorName


def normalize_doctor_full_name(value: str | None) -> str | None:
    """Приводит ФИО к одной строке без лишних пробелов; пустое значение -> None."""

    normalized = " ".join(str(value or "").split()).strip()
    return normalized or None


def get_center_doctor_names(db: Session, center_id: int | None) -> dict[str, str]:
    """ФИО врачей этого медцентра по коду специальности.

    Без центра справочник пустой: общего на всю базу списка врачей больше нет, и
    подставлять чужой центр нельзя.
    """

    if not center_id:
        return {}

    rows = db.execute(
        select(CenterDoctorName.doctor_role_code, CenterDoctorName.full_name).where(
            CenterDoctorName.center_id == center_id
        )
    ).all()
    return {
        str(code).strip(): str(full_name).strip()
        for code, full_name in rows
        if str(code or "").strip() and str(full_name or "").strip()
    }


def set_center_doctor_name(db: Session, center_id: int, role_code: str, full_name: str | None) -> str | None:
    """Записывает ФИО врача для медцентра и возвращает сохранённое значение."""

    normalized_code = str(role_code or "").strip()
    normalized_name = normalize_doctor_full_name(full_name)
    entry = db.execute(
        select(CenterDoctorName).where(
            CenterDoctorName.center_id == center_id,
            CenterDoctorName.doctor_role_code == normalized_code,
        )
    ).scalar_one_or_none()

    if entry is None:
        entry = CenterDoctorName(
            center_id=center_id,
            doctor_role_code=normalized_code,
            full_name=normalized_name,
        )
        db.add(entry)
    else:
        entry.full_name = normalized_name

    return normalized_name
