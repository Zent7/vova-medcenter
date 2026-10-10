from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

try:
    import xlrd
except ImportError as exc:  # pragma: no cover - depends on local setup
    raise SystemExit("Install Excel support first: python -m pip install -r requirements.txt") from exc

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models.center import Center
from app.models.client import Client
from app.models.user import User

DEFAULT_SEARCH_DIRS = [
    Path.home() / "Downloads" / "Telegram Desktop",
    Path.home() / "Downloads",
    ROOT_DIR / "storage" / "imports",
]

PATIENT_SHEET = "ПАЦИЕНТЫ"
HEADER_ROW = 4
FIRST_DATA_ROW = 5

FIELD_BY_COLUMN = {
    3: "full_name",
    4: "birth_date",
    5: "registration_text",
    6: "admission_category",
    7: "reference_number",
    8: "doctor_gynecologist",
    9: "doctor_stomatologist",
    10: "doctor_dermatologist",
    11: "doctor_neurologist",
    12: "doctor_surgeon",
    13: "doctor_otolaryngologist",
    14: "doctor_ophthalmologist",
    15: "doctor_therapist",
    16: "doctor_psychiatrist",
    17: "doctor_infectionist",
    18: "doctor_phthisiatrician",
    19: "doctor_uzist",
    20: "indications",
    21: "notes",
    22: "encounter_date_text",
    23: "card_number",
    24: "journal_number",
    25: "no_number",
    26: "flg",
    27: "organization",
    28: "mkb10",
    29: "real_date_text",
}


def find_latest_excel() -> Path:
    candidates: list[Path] = []
    for directory in DEFAULT_SEARCH_DIRS:
        if directory.exists():
            candidates.extend(directory.glob("Водитель 2.0*.xls"))
    if not candidates:
        raise SystemExit("Не нашел файл Водитель 2.0*.xls в Downloads/Telegram Desktop или storage/imports.")
    return max(candidates, key=lambda item: item.stat().st_mtime)


def cell_text(sheet: xlrd.sheet.Sheet, row_index: int, column_index: int) -> str | None:
    cell = sheet.cell(row_index, column_index)
    if cell.ctype in {xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK}:
        return None
    if cell.ctype == xlrd.XL_CELL_DATE:
        value = xlrd.xldate_as_datetime(cell.value, sheet.book.datemode)
        if value.time() == time.min:
            return value.strftime("%d.%m.%Y")
        return value.strftime("%d.%m.%Y %H:%M")
    if cell.ctype == xlrd.XL_CELL_NUMBER:
        number = float(cell.value)
        if number.is_integer():
            return str(int(number))
        return str(number).replace(".", ",")
    value = str(cell.value).strip()
    return value or None


def cell_int(sheet: xlrd.sheet.Sheet, row_index: int, column_index: int) -> int | None:
    text = cell_text(sheet, row_index, column_index)
    if not text:
        return None
    try:
        return int(float(text.replace(",", ".")))
    except ValueError:
        return None


def cell_date(sheet: xlrd.sheet.Sheet, row_index: int, column_index: int) -> date:
    cell = sheet.cell(row_index, column_index)
    if cell.ctype == xlrd.XL_CELL_DATE:
        return xlrd.xldate_as_datetime(cell.value, sheet.book.datemode).date()
    text = cell_text(sheet, row_index, column_index)
    if text:
        for date_format in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%Y %H:%M"):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue
    return date(1900, 1, 1)


def split_full_name(value: str | None) -> tuple[str, str, str | None]:
    parts = (value or "").split()
    if not parts:
        return "Без фамилии", "Без имени", None
    return parts[0], parts[1] if len(parts) > 1 else "Без имени", " ".join(parts[2:]) or None


def get_default_user_id(db: Session) -> int | None:
    return db.execute(select(User.id).order_by(User.id)).scalar_one_or_none()


def read_patient_rows(path: Path) -> list[dict[str, Any]]:
    book = xlrd.open_workbook(str(path))
    sheet = book.sheet_by_name(PATIENT_SHEET)
    rows: list[dict[str, Any]] = []

    for row_index in range(FIRST_DATA_ROW, sheet.nrows):
        full_name = cell_text(sheet, row_index, 3)
        if not full_name:
            continue

        patient_number = cell_int(sheet, row_index, 1)
        legacy_source_id = cell_int(sheet, row_index, 0)
        if patient_number is None:
            continue

        payload: dict[str, Any] = {
            "legacy_source_id": legacy_source_id,
            "patient_number": patient_number,
            "birth_date": cell_date(sheet, row_index, 4),
            "legacy_payload_json": {},
        }
        last_name, first_name, middle_name = split_full_name(full_name)
        payload["last_name"] = last_name
        payload["first_name"] = first_name
        payload["middle_name"] = middle_name

        for column_index, field_name in FIELD_BY_COLUMN.items():
            value = cell_text(sheet, row_index, column_index)
            if field_name == "full_name" or field_name == "birth_date":
                continue
            payload[field_name] = value
            payload["legacy_payload_json"][field_name] = value

        payload["address_text"] = payload.get("registration_text")
        rows.append(payload)

    return rows


def upsert_clients(db: Session, rows: list[dict[str, Any]]) -> tuple[int, int]:
    created = 0
    updated = 0
    default_user_id = get_default_user_id(db)
    # Клиент без центра не виден ни одному сотруднику: такие попадают в первый центр,
    # как клиенты без обращений при миграции 0024. Клиент с центрами не переносится.
    default_center = db.execute(select(Center).order_by(Center.id)).scalars().first()

    for payload in rows:
        legacy_source_id = payload.get("legacy_source_id")
        patient_number = payload["patient_number"]
        client = None
        if legacy_source_id is not None:
            client = db.execute(select(Client).where(Client.legacy_source_id == legacy_source_id)).scalar_one_or_none()
        if client is None:
            client = db.execute(select(Client).where(Client.patient_number == patient_number)).scalar_one_or_none()

        if client is None:
            client = Client(created_by_user_id=default_user_id, **payload)
            db.add(client)
            created += 1
        else:
            for key, value in payload.items():
                setattr(client, key, value)
            updated += 1

        if default_center is not None and not client.center_ids:
            client.centers.append(default_center)

    db.commit()
    return created, updated


def preview(path: Path) -> None:
    rows = read_patient_rows(path)
    print(f"Файл: {path}")
    print(f"Клиентов на листе {PATIENT_SHEET}: {len(rows)}")
    for row in rows[:5]:
        print(f"{row['patient_number']}: {row['last_name']} {row['first_name']} {row.get('middle_name') or ''}".strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Import clients from legacy Водитель 2.0.xls workbook.")
    parser.add_argument("--file", type=Path, default=None, help="Path to Водитель 2.0.xls")
    parser.add_argument("--preview", action="store_true", help="Only show detected rows, do not write to DB")
    args = parser.parse_args()

    path = args.file or find_latest_excel()
    if not path.exists():
        raise SystemExit(f"Файл не найден: {path}")

    rows = read_patient_rows(path)
    if args.preview:
        preview(path)
        return

    init_db()
    with SessionLocal() as db:
        created, updated = upsert_clients(db, rows)
    print(f"Импорт завершен. Создано: {created}. Обновлено: {updated}. Файл: {path}")


if __name__ == "__main__":
    main()
