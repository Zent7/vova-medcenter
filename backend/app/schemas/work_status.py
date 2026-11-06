from datetime import date, datetime

from pydantic import BaseModel


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


class WorkStatusMonthRead(BaseModel):
    year: int
    month: int
    days_in_month: int
    today: date
    now: datetime
    open: WorkStatusOpenRead | None = None
    days: list[WorkStatusDayRead]
    totals: WorkStatusTotalsRead
