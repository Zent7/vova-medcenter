from datetime import time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError


# Смену админ выбирает вручную из этих пяти вариантов.
SchedulePattern = Literal["2/2", "3/3", "4/4", "5/2", "6/1"]


class RoleRead(BaseModel):
    id: int
    code: str
    name: str
    description: str | None = None

    model_config = {"from_attributes": True}


class StaffCenterRead(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class StaffCenterScheduleRead(BaseModel):
    # График сотрудника в одном медцентре: у каждого медцентра свой шаблон и время смены.
    center_id: int
    center_name: str
    pattern: str = Field(validation_alias="schedule_pattern")
    shift_start: time = Field(validation_alias="schedule_start")
    shift_end: time = Field(validation_alias="schedule_end")

    model_config = {"from_attributes": True}


class StaffCenterScheduleCreate(BaseModel):
    center_id: int
    pattern: SchedulePattern
    # Время «со скольку — до скольки»; конец может быть раньше начала (ночная смена).
    shift_start: time
    shift_end: time


class StaffUserRead(BaseModel):
    id: int
    login: str
    full_name: str
    email: str | None = None
    is_active: bool
    role: RoleRead
    # Основной медцентр: в нём сотрудник оказывается при входе. У админа его нет —
    # он видит все центры.
    center_id: int | None = Field(default=None, validation_alias="pinned_center_id")
    center_name: str | None = Field(default=None, validation_alias="pinned_center_name")
    all_centers: bool = Field(default=False, validation_alias="sees_all_centers")
    # Все центры, где сотрудник может работать, основной первым; у админа пусто.
    centers: list[StaffCenterRead] = Field(default_factory=list, validation_alias="work_centers")
    # Графики по медцентрам; в медцентре без графика строки нет.
    schedules: list[StaffCenterScheduleRead] = Field(default_factory=list, validation_alias="center_schedules")
    # Ставка за час; None, если не задана.
    hourly_rate: Decimal | None = None

    model_config = {"from_attributes": True}


class StaffUserCreate(BaseModel):
    login: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=1, max_length=100)
    full_name: str = Field(min_length=1, max_length=255)
    email: str | None = None
    role_code: str = Field(min_length=3, max_length=50)
    # Медцентры, в которых работает сотрудник; первый — основной. Для админа не
    # нужны: он видит все. `center_id` — прежний вариант с одним центром, его ещё
    # может прислать вкладка со старой версией страницы.
    center_ids: list[int] | None = None
    center_id: int | None = None
    # Графики по медцентрам: в каждом отмеченном медцентре свой шаблон и время смены.
    schedules: list[StaffCenterScheduleCreate] = Field(default_factory=list)
    # Ставка за час в рублях, до копеек; общая для учетки, можно не указывать.
    hourly_rate: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)

    @field_validator("login", "password", "full_name", "role_code", mode="before")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Поле не должно быть пустым")
        return normalized

    @property
    def requested_center_ids(self) -> list[int]:
        if self.center_ids is not None:
            return self.center_ids
        return [] if self.center_id is None else [self.center_id]

    @field_validator("email", mode="before")
    @classmethod
    def strip_optional_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class StaffUserDeleteResponse(BaseModel):
    # deleted=False: по учетной записи есть записи в программе, поэтому ее только отключили.
    deleted: bool
    message: str


class StaffCentersUpdate(BaseModel):
    # Первый центр становится основным, остальные — дополнительными.
    center_ids: list[int]


class StaffScheduleUpdate(BaseModel):
    # Графики всех медцентров сотрудника целиком: медцентр, которого нет в списке, остается без графика.
    # Поле обязательно, чтобы пустой запрос не стер графики молча.
    schedules: list[StaffCenterScheduleCreate]
    hourly_rate: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)


class StaffEmailUpdate(BaseModel):
    # Почта сотрудника: на нее приходят уведомления админам. Пустое значение ее убирает.
    email: str | None = None

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            return None
        local, sep, domain = normalized.partition("@")
        valid = bool(local) and bool(sep) and "." in domain.strip(".") and "@" not in domain and " " not in normalized
        if not valid or len(normalized) > 255:
            # PydanticCustomError, а не ValueError: у ValueError Pydantic добавляет префикс «Value error, » в текст ошибки.
            raise PydanticCustomError("staff_email_format", "Укажите почту в формате name@example.com")
        return normalized
