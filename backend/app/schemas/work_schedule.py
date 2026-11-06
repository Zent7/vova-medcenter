from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field


# Ответы таблицы и статистики. Времени — строки «ЧЧ:ММ», часы и суммы — числа с копейками.


class WorkScheduleCenterRead(BaseModel):
    id: int
    name: str
    color: str | None = None


class WorkScheduleDayRead(BaseModel):
    work_date: date
    kind: Literal["shift", "dayoff", "sick", "vacation"]
    start_time: str | None = None
    end_time: str | None = None
    fact_start_time: str | None = None
    fact_end_time: str | None = None
    source: Literal["pattern", "manual"]
    # Номер смены в цикле шаблона: 1 — первая смена цикла. Пусто у ручных смен без шаблона.
    shift_no: int | None = None


class WorkScheduleRowRead(BaseModel):
    user_id: int
    full_name: str
    role_code: str
    role_name: str
    is_active: bool
    center: WorkScheduleCenterRead | None = None
    pattern: str | None = None
    shift_start: str | None = None
    shift_end: str | None = None
    days: list[WorkScheduleDayRead] = Field(default_factory=list)


class WorkScheduleMonthRead(BaseModel):
    year: int
    month: int
    days_in_month: int
    # Админ редактирует таблицу; врач и оператор только смотрят.
    can_edit: bool
    centers: list[WorkScheduleCenterRead] = Field(default_factory=list)
    rows: list[WorkScheduleRowRead] = Field(default_factory=list)


class WorkScheduleHoursDayRead(BaseModel):
    work_date: date
    plan_hours: float
    fact_hours: float


class WorkScheduleTotalsRead(BaseModel):
    days: int
    hours: float
    # Часы × ставка; None, если ставка у сотрудника не задана.
    amount: float | None = None


class WorkScheduleStatsRowRead(BaseModel):
    user_id: int
    full_name: str
    role_name: str
    center_name: str | None = None
    pattern: str | None = None
    shift_start: str | None = None
    shift_end: str | None = None
    hourly_rate: float | None = None
    days: list[WorkScheduleHoursDayRead] = Field(default_factory=list)
    plan: WorkScheduleTotalsRead
    fact: WorkScheduleTotalsRead


class WorkScheduleStatsRead(BaseModel):
    year: int
    month: int
    days_in_month: int
    rows: list[WorkScheduleStatsRowRead] = Field(default_factory=list)


class WorkScheduleGenerateRead(BaseModel):
    created: int
    # Сотрудники с шаблоном, у которых еще не назначена первая смена.
    users_without_start: list[str] = Field(default_factory=list)


class WorkScheduleChangeRead(BaseModel):
    changed: int


# Тела запросов.


class WorkScheduleGenerate(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class WorkScheduleDayUpdate(BaseModel):
    kind: Literal["shift", "dayoff", "sick", "vacation"]
    # Для смены — «со скольки» и «до скольки»; конец может быть раньше начала (ночная смена).
    start_time: time | None = None
    end_time: time | None = None


class WorkScheduleAbsenceCreate(BaseModel):
    kind: Literal["sick", "vacation"]
    date_from: date
    date_to: date


class WorkScheduleFirstShift(BaseModel):
    work_date: date


class WorkScheduleFactItem(BaseModel):
    work_date: date
    # Оба пустые — факт равен плану.
    start_time: time | None = None
    end_time: time | None = None


class WorkScheduleFactsUpdate(BaseModel):
    items: list[WorkScheduleFactItem] = Field(min_length=1, max_length=62)
