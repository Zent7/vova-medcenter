from datetime import date, datetime

from pydantic import BaseModel, Field


class WorkStatusOpenRead(BaseModel):
    started_at: datetime
    elapsed_seconds: int


class WorkStatusDayRead(BaseModel):
    work_date: date
    kind: str | None = None
    plan_hours: float
    fact_hours: float
    overtime_hours: float


class WorkStatusTotalsRead(BaseModel):
    plan_hours: float
    fact_hours: float
    overtime_hours: float


class WorkStatusMarkRead(BaseModel):
    """Отметка «На работу» — «С работы». Пока ended_at пуст, отметка открыта, а длительность идет до now."""

    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int


class WorkStatusMonthRead(BaseModel):
    year: int
    month: int
    days_in_month: int
    today: date
    now: datetime
    open: WorkStatusOpenRead | None = None
    days: list[WorkStatusDayRead]
    marks: list[WorkStatusMarkRead] = Field(default_factory=list)
    totals: WorkStatusTotalsRead
