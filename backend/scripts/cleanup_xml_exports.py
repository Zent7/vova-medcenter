from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.xml_exports import cleanup_old_xml_exports  # noqa: E402


def main() -> None:
    with SessionLocal() as db:
        result = cleanup_old_xml_exports(db)
        db.commit()
        print(
            {
                "deleted_count": result.deleted_count,
                "missing_count": result.missing_count,
                "retention_days": settings.xml_exports_retention_days,
            }
        )


if __name__ == "__main__":
    main()
