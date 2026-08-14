from sqlalchemy import text

from fastapi import APIRouter

from app.core.config import settings
from app.db.session import engine

router = APIRouter()


@router.get("/health")
def healthcheck() -> dict[str, str | bool]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    return {
        "status": "ok",
        "database_ok": True,
        "database_dialect": engine.dialect.name,
        "database_url": engine.url.render_as_string(hide_password=True),
        "build_revision": settings.build_revision,
    }
