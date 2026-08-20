from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MedCenters API"
    app_env: str = "dev"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://medcenters:medcenters@127.0.0.1:5434/medcenters"
    allow_sqlite: bool = False
    frontend_origin: str = "http://localhost:5173"
    public_frontend_origin: str = "https://demo.med-center.online"
    build_revision: str = "development"
    generated_documents_dir: str = "storage/generated"
    document_template_overrides_dir: str = "storage/template-overrides"
    xml_exports_retention_days: int = 30
    xml_exports_timezone: str = "Europe/Moscow"
    deletion_notify_email: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @model_validator(mode="after")
    def validate_database_backend(self) -> "Settings":
        if self.database_url.startswith("sqlite") and not self.allow_sqlite:
            raise ValueError(
                "SQLite is disabled for the working backend. "
                "Use PostgreSQL in DATABASE_URL or explicitly set ALLOW_SQLITE=true for temporary local diagnostics."
            )
        return self


settings = Settings()
