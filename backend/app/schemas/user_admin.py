from pydantic import BaseModel, Field, field_validator


class RoleRead(BaseModel):
    id: int
    code: str
    name: str
    description: str | None = None

    model_config = {"from_attributes": True}


class StaffUserRead(BaseModel):
    id: int
    login: str
    full_name: str
    email: str | None = None
    is_active: bool
    role: RoleRead
    # Закреплённый медцентр; у админа его нет — он видит все центры.
    center_id: int | None = Field(default=None, validation_alias="pinned_center_id")
    center_name: str | None = Field(default=None, validation_alias="pinned_center_name")
    all_centers: bool = Field(default=False, validation_alias="sees_all_centers")

    model_config = {"from_attributes": True}


class StaffUserCreate(BaseModel):
    login: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=1, max_length=100)
    full_name: str = Field(min_length=1, max_length=255)
    email: str | None = None
    role_code: str = Field(min_length=3, max_length=50)
    # Медцентр, в котором работает сотрудник. Для админа не нужен: он видит все.
    center_id: int | None = None

    @field_validator("login", "password", "full_name", "role_code", mode="before")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Поле не должно быть пустым")
        return normalized

    @field_validator("email", mode="before")
    @classmethod
    def strip_optional_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None
