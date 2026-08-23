from pydantic import BaseModel, Field


class CenterRead(BaseModel):
    id: int
    code: str
    name: str
    is_active: bool

    model_config = {"from_attributes": True}


class CenterNumberingUpdate(BaseModel):
    """Последний номер справки ЛМК из бумажного журнала медцентра."""

    lmk_certificate_last_number: int | None = Field(default=None, ge=0)


class CenterNumberingRead(BaseModel):
    center_id: int
    lmk_certificate_last_number: int | None = None
    # Номер, который получит следующая справка: после первой печати счёт ведёт
    # уже выданная справка, а не только последний номер бумажного журнала.
    lmk_certificate_next_number: int
