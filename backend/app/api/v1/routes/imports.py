from __future__ import annotations

import base64
import io
import json
import posixpath
import re
import zipfile
from collections import OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import xlrd
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.center import Center
from app.models.client import Client
from app.models.encounter import Encounter
from app.models.encounter_service import EncounterService
from app.models.service import Service
from app.models.user import User
from app.models.visit_type import VisitType
from app.api.v1.routes.encounters import sync_primary_payment
from app.services.audit import write_audit_log
from app.services.medical_autofill import autofill_completed_doctors_for_service
from app.services.system_user import get_system_user_id
from app.schemas.imports import (
    ClientImportExcelRequest,
    ClientImportPreviewResponse,
    ClientImportPreviewRow,
    ClientImportResultResponse,
)

router = APIRouter()


ROOT_DIR = Path(__file__).resolve().parents[5]
LEGACY_DATA_PATHS = [
    ROOT_DIR / "demo" / "legacy-data.js",
    ROOT_DIR / "frontend" / "public" / "demo" / "legacy-data.js",
]

CLIENT_IMPORT_HEADER_ALIASES = {
    "patient_number": ("№ пациента", "Номер пациента"),
    "last_name": ("Фамилия",),
    "first_name": ("Имя",),
    "middle_name": ("Отчество",),
    "birth_date": ("Дата рождения", "Дата рождения (формат 31.12.2026)"),
    "sex": ("Пол",),
    "phone": ("Телефон",),
    "email": ("E-mail", "Email", "Электронная почта"),
    "document_type": ("Тип документа",),
    "document_series": ("Серия документа",),
    "document_number": ("Номер документа", "№ документа"),
    "document_issued_by": ("Кем выдан",),
    "document_issued_date": ("Дата выдачи",),
    "snils": ("СНИЛС",),
    "registration_text": ("Регистрация", "Адрес регистрации"),
    "registration_region": ("Адрес Регистрация-ОБЛОСТЬ", "Область регистрации"),
    "registration_city": ("Адрес Регистрация-ГОРОД", "Город регистрации"),
    "registration_street": ("Адрес Регистрация-УЛИЦА", "Улица регистрации"),
    "registration_house": ("Адрес Регистрация-НОМЕР ДОМА", "Номер дома", "Дом"),
    "registration_building": ("корпус, литер, строение", "Корпус", "Строение"),
    "registration_apartment": ("квартира", "Квартира"),
    "address_text": ("Адрес проживания",),
    "organization": ("Организация", "Название Организация", "Название организации"),
    "profession": ("Должность", "Профессия"),
    "indications": ("Вредные произв. Факторы", "Вредные производственные факторы"),
    "flg": ("ФЛГ от", "ФЛГ"),
    "service": ("Услуга",),
    "encounter_date": ("Дата обращения",),
    "admission_category": ("Категория допуска",),
    "reference_number": ("№ справки", "Номер справки"),
    "notes": ("Примечание",),
}

NEW_CLIENT_TEMPLATE_MARKERS = {
    "registration_region",
    "registration_city",
    "registration_street",
    "registration_house",
    "registration_building",
    "registration_apartment",
    "profession",
    "indications",
    "flg",
}

MEDICAL_DOCUMENT_IMPORT_RULES = {
    "лмк": ("lmk_new", 18, ("ЛМК",)),
    "продление лмк": ("lmk_extend", 19, ("Продление ЛМК",)),
    "проф": ("prof", 16, ("Профосмотр",)),
    "профосмотр": ("prof", 16, ("Профосмотр",)),
    "водительская": ("driver", 8, ("Медицинская комиссия", "Водительская справка")),
    "водительская справка": ("driver", 8, ("Медицинская комиссия", "Водительская справка")),
    "тракторная": ("tractor", 7, ("071У", "Справка 071У")),
    "тракторная справка": ("tractor", 7, ("071У", "Справка 071У")),
    "гимс": ("gims", 37, ("ГИМС",)),
}


def _normalize_header_key(value: str | None) -> str:
    text = str(value or "").strip().casefold().replace("ё", "е").replace("№", " номер ")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


HEADER_TO_FIELD = {
    _normalize_header_key(header): field
    for field, aliases in CLIENT_IMPORT_HEADER_ALIASES.items()
    for header in aliases
}
XLSX_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkg": "http://schemas.openxmlformats.org/package/2006/relationships",
}


class ClientImportHeaderError(ValueError):
    pass


def extract_window_json(source: str, variable_name: str) -> Any:
    pattern = rf"window\.{re.escape(variable_name)}\s*=\s*(.*?);(?=\s*window\.|\s*$)"
    match = re.search(pattern, source, flags=re.S)
    if not match:
        raise ValueError(f"Не найден блок {variable_name}")
    return json.loads(match.group(1))


def split_full_name(full_name: str | None) -> tuple[str, str, str | None]:
    parts = str(full_name or "").strip().split()
    if not parts:
        return "Без фамилии", "Без имени", None
    return parts[0], parts[1] if len(parts) > 1 else "Без имени", " ".join(parts[2:]) or None


def parse_date(value: str | None) -> date:
    text = str(value or "").strip()
    for date_format in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    parsed_short_date = parse_short_ru_date(text)
    if parsed_short_date is not None:
        return parsed_short_date
    return date(1900, 1, 1)


def parse_optional_date(value: str | None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    for date_format in ("%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    if re.fullmatch(r"\d+(?:[.,]\d+)?", text):
        try:
            serial = float(text.replace(",", "."))
        except ValueError:
            serial = 0
        if 1 <= serial <= 100000:
            return (datetime(1899, 12, 30) + timedelta(days=serial)).date()
    parsed_short_date = parse_short_ru_date(text)
    if parsed_short_date is not None:
        return parsed_short_date
    return None


def parse_short_ru_date(value: str) -> date | None:
    match = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{2})(?:\s+\d{1,2}:\d{2})?", value)
    if not match:
        return None
    day, month, year = match.groups()
    current_year = date.today().year
    current_century = current_year // 100 * 100
    full_year = (current_century if int(year) <= current_year % 100 + 20 else current_century - 100) + int(year)
    try:
        return date(full_year, int(month), int(day))
    except ValueError:
        return None


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_header(value: str | None) -> str:
    return _normalize_header_key(value)


def parse_int(value: Any) -> int | None:
    text = normalize_text(value)
    if not text:
        return None
    try:
        return int(float(text.replace(",", ".")))
    except ValueError:
        return None


def column_letters_to_index(value: str) -> int:
    result = 0
    for char in value:
        if not char.isalpha():
            break
        result = result * 26 + (ord(char.upper()) - 64)
    return result - 1


def read_xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root.findall("main:si", XLSX_NS):
        texts = [node.text or "" for node in item.findall(".//main:t", XLSX_NS)]
        values.append("".join(texts))
    return values


def resolve_sheet_paths(archive: zipfile.ZipFile) -> list[str]:
    workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
    workbook_rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in workbook_rels.findall("pkg:Relationship", XLSX_NS)
    }
    sheets = workbook_root.findall("main:sheets/main:sheet", XLSX_NS)
    if not sheets:
        raise ValueError("В Excel-файле не найден лист с данными")

    paths: list[str] = []
    for sheet in sheets:
        relation_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = rel_targets.get(relation_id or "")
        if not target:
            continue
        normalized_target = target.lstrip("/")
        if not normalized_target.startswith("xl/"):
            normalized_target = posixpath.normpath(posixpath.join("xl", normalized_target))
        if normalized_target in archive.namelist():
            paths.append(normalized_target)
    if not paths:
        raise ValueError("Не удалось открыть листы Excel-файла")
    return paths


def read_xlsx_sheet_rows(
    archive: zipfile.ZipFile,
    sheet_path: str,
    shared_strings: list[str],
) -> list[dict[int, str | None]]:
    root = ET.fromstring(archive.read(sheet_path))
    rows: list[dict[int, str | None]] = []
    for row in root.findall(".//main:sheetData/main:row", XLSX_NS):
        cells: dict[int, str | None] = {}
        for cell in row.findall("main:c", XLSX_NS):
            ref = cell.attrib.get("r", "")
            column_index = column_letters_to_index(ref)
            cell_type = cell.attrib.get("t")
            value = None
            if cell_type == "s":
                index_text = cell.findtext("main:v", default="", namespaces=XLSX_NS)
                if index_text:
                    value = shared_strings[int(index_text)]
            elif cell_type == "inlineStr":
                texts = [node.text or "" for node in cell.findall(".//main:t", XLSX_NS)]
                value = "".join(texts)
            else:
                value = cell.findtext("main:v", default=None, namespaces=XLSX_NS)
            cells[column_index] = normalize_text(value)
        rows.append(cells)
    return rows


def read_xlsx_rows(content: bytes) -> list[dict[str, Any]]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        shared_strings = read_xlsx_shared_strings(archive)
        for sheet_path in resolve_sheet_paths(archive):
            rows = read_xlsx_sheet_rows(archive, sheet_path, shared_strings)
            try:
                return rows_to_client_records(rows)
            except ClientImportHeaderError:
                continue
    raise ClientImportHeaderError("В Excel-шаблоне не хватает обязательных колонок Фамилия и Имя")


def read_xls_rows(content: bytes) -> list[dict[str, Any]]:
    book = xlrd.open_workbook(file_contents=content)
    for sheet in book.sheets():
        rows: list[dict[int, str | None]] = []
        for row_index in range(sheet.nrows):
            cells: dict[int, str | None] = {}
            for column_index in range(sheet.ncols):
                cell = sheet.cell(row_index, column_index)
                if cell.ctype in {xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK}:
                    cells[column_index] = None
                elif cell.ctype == xlrd.XL_CELL_DATE:
                    cells[column_index] = xlrd.xldate_as_datetime(cell.value, book.datemode).strftime("%d.%m.%y")
                elif cell.ctype == xlrd.XL_CELL_NUMBER:
                    number = float(cell.value)
                    cells[column_index] = str(int(number)) if number.is_integer() else str(number)
                else:
                    cells[column_index] = normalize_text(cell.value)
            rows.append(cells)
        try:
            return rows_to_client_records(rows)
        except ClientImportHeaderError:
            continue
    raise ClientImportHeaderError("В Excel-шаблоне не хватает обязательных колонок Фамилия и Имя")


def compose_registration_text(row: dict[str, Any]) -> str | None:
    explicit = normalize_text(row.get("registration_text"))
    if explicit:
        return explicit

    parts = [
        normalize_text(row.get("registration_region")),
        normalize_text(row.get("registration_city")),
        normalize_text(row.get("registration_street")),
    ]
    house = normalize_text(row.get("registration_house"))
    building = normalize_text(row.get("registration_building"))
    apartment = normalize_text(row.get("registration_apartment"))
    if house:
        parts.append(house if re.match(r"^(?:д\.?|дом)\s*", house, re.I) else f"д. {house}")
    if building:
        parts.append(
            building
            if re.match(r"^(?:корп\.?|корпус|стр\.?|строение|литер)\s*", building, re.I)
            else f"корп./стр. {building}"
        )
    if apartment:
        parts.append(apartment if re.match(r"^(?:кв\.?|квартира)\s*", apartment, re.I) else f"кв. {apartment}")
    return ", ".join(part for part in parts if part) or None


def rows_to_client_records(rows: list[dict[int, str | None]]) -> list[dict[str, Any]]:
    if not rows:
        return []

    header_index = -1
    columns: dict[int, str] = {}
    for candidate_index, header_row in enumerate(rows[:50]):
        candidate_columns: dict[int, str] = {}
        for index, value in header_row.items():
            field_name = HEADER_TO_FIELD.get(normalize_header(value))
            if field_name:
                candidate_columns[index] = field_name
        if "last_name" in candidate_columns.values() and "first_name" in candidate_columns.values():
            header_index = candidate_index
            columns = candidate_columns
            break

    if header_index < 0:
        raise ClientImportHeaderError("В Excel-шаблоне не хватает обязательных колонок Фамилия и Имя")

    if NEW_CLIENT_TEMPLATE_MARKERS.intersection(columns.values()):
        columns = {
            index: "medical_document_type" if field_name == "document_type" else field_name
            for index, field_name in columns.items()
        }

    records: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        payload: dict[str, Any] = {"row_number": row_number}
        for column_index, field_name in columns.items():
            value = normalize_text(row.get(column_index))
            payload[field_name] = value

        client_values = [
            value
            for field_name, value in payload.items()
            if field_name not in {"row_number", "medical_document_type"}
        ]
        if not any(client_values):
            continue

        payload["patient_number"] = parse_int(payload.get("patient_number"))
        for field_name in ("birth_date", "document_issued_date", "encounter_date"):
            raw_value = payload.get(field_name)
            payload[f"_{field_name}_invalid"] = bool(raw_value and parse_optional_date(raw_value) is None)
            payload[field_name] = parse_optional_date(raw_value)
        flg_date = parse_optional_date(payload.get("flg"))
        if flg_date is not None:
            payload["flg"] = flg_date.strftime("%d.%m.%Y")
        payload["registration_text"] = compose_registration_text(payload)
        records.append(payload)

    return records


def decode_excel_payload(payload: ClientImportExcelRequest) -> bytes:
    try:
        return base64.b64decode(payload.file_content_base64)
    except Exception as exc:  # pragma: no cover - invalid input from client
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось прочитать содержимое файла") from exc


def read_client_excel_rows(payload: ClientImportExcelRequest) -> list[dict[str, Any]]:
    content = decode_excel_payload(payload)
    suffix = Path(payload.file_name).suffix.lower()
    if suffix == ".xlsx":
        return read_xlsx_rows(content)
    if suffix == ".xls":
        return read_xls_rows(content)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Поддерживаются только файлы .xlsx и .xls",
    )


def validate_client_import_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(
            "В Excel-файле не найдено ни одной заполненной строки. "
            "Заполняйте первый лист, начиная со строки 2."
        )

    errors: list[str] = []
    for row in rows:
        row_number = row.get("row_number", "?")
        if not normalize_text(row.get("last_name")):
            errors.append(f"строка {row_number}: не заполнена фамилия")
        if not normalize_text(row.get("first_name")):
            errors.append(f"строка {row_number}: не заполнено имя")
        if row.get("_birth_date_invalid"):
            errors.append(f"строка {row_number}: неверная дата рождения")
        elif row.get("birth_date") is None:
            errors.append(f"строка {row_number}: не заполнена дата рождения")
        if row.get("_document_issued_date_invalid"):
            errors.append(f"строка {row_number}: неверная дата выдачи документа")
        if row.get("_encounter_date_invalid"):
            errors.append(f"строка {row_number}: неверная дата обращения")

    if errors:
        shown_errors = errors[:10]
        suffix = f" Ещё ошибок: {len(errors) - len(shown_errors)}." if len(errors) > len(shown_errors) else ""
        raise ValueError("Не удалось проверить Excel: " + "; ".join(shown_errors) + "." + suffix)


def json_safe_import_row(row: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in row.items():
        if key.startswith("_"):
            continue
        if isinstance(value, (date, datetime)):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


def normalize_service_lookup(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def service_import_label(service: Service) -> str:
    price = Decimal(service.price or 0)
    price_text = f"{price:,.2f}".replace(",", "\u00a0").rstrip("0").rstrip(".")
    return f"{service.name} — {price_text} ₽"


def build_service_lookup(services: list[Service]) -> dict[str, list[Service]]:
    lookup: dict[str, list[Service]] = {}
    for service in services:
        for value in (service.code, service.name, service_import_label(service)):
            key = normalize_service_lookup(value)
            if key:
                lookup.setdefault(key, []).append(service)
    return lookup


def resolve_medical_document_rule(value: object) -> tuple[str, int, tuple[str, ...]] | None:
    key = _normalize_header_key(normalize_text(value))
    return MEDICAL_DOCUMENT_IMPORT_RULES.get(key)


def resolve_import_service(
    row: dict[str, Any],
    service_lookup: dict[str, list[Service]],
    services: list[Service],
) -> Service | None:
    value = normalize_text(row.get("service"))
    row_number = row.get("row_number", "?")
    if value:
        matches = service_lookup.get(normalize_service_lookup(value), [])
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(
                f'Строка {row_number}: услуга "{value}" неоднозначна. '
                "Выберите вариант из выпадающего списка с ценой."
            )
        raise ValueError(
            f'Строка {row_number}: услуга "{value}" не найдена или неактивна. '
            "Выберите значение из выпадающего списка."
        )

    document_type = normalize_text(row.get("medical_document_type"))
    if not document_type:
        return None
    rule = resolve_medical_document_rule(document_type)
    if rule is None:
        raise ValueError(
            f'Строка {row_number}: тип документа "{document_type}" не распознан. '
            "Допустимы ЛМК, Продление ЛМК, Проф, Водительская, Тракторная и ГИМС."
        )

    _, preferred_legacy_id, fallback_names = rule
    preferred = [service for service in services if service.legacy_source_id == preferred_legacy_id]
    if preferred:
        return sorted(preferred, key=lambda service: service.id)[0]
    for name in fallback_names:
        matches = service_lookup.get(normalize_service_lookup(name), [])
        if matches:
            return sorted(matches, key=lambda service: service.id)[0]
    raise ValueError(
        f'Строка {row_number}: для типа документа "{document_type}" не найдена активная услуга.'
    )


def resolve_import_visit_type(
    row: dict[str, Any],
    visit_type_by_code: dict[str, VisitType],
) -> VisitType | None:
    document_type = normalize_text(row.get("medical_document_type"))
    if not document_type:
        return None
    rule = resolve_medical_document_rule(document_type)
    if rule is None:
        return None
    return visit_type_by_code.get(rule[0])


def get_import_services(db: Session) -> list[Service]:
    return db.execute(
        select(Service)
        .where(Service.is_active.is_(True))
        .order_by(Service.name.asc(), Service.price.asc(), Service.id.asc())
    ).scalars().all()


def get_import_visit_types(db: Session) -> dict[str, VisitType]:
    visit_types = db.execute(
        select(VisitType).where(VisitType.is_active.is_(True)).order_by(VisitType.id.asc())
    ).scalars().all()
    return {visit_type.code: visit_type for visit_type in visit_types}


def get_import_center(db: Session, actor_user_id: int | None) -> Center | None:
    if actor_user_id is not None:
        actor = db.get(User, actor_user_id)
        if actor is not None and actor.center_id is not None:
            center = db.get(Center, actor.center_id)
            if center is not None and center.is_active:
                return center
    return db.execute(
        select(Center).where(Center.is_active.is_(True)).order_by(Center.id.asc())
    ).scalars().first()


def dedupe_legacy_clients(clients: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_legacy_key: OrderedDict[int | str, dict[str, Any]] = OrderedDict()
    for item in clients:
        legacy_source_id = int(item.get("id") or 0) or None
        patient_number = int(item.get("patientNumber") or 0)
        if not patient_number:
            continue
        by_legacy_key[legacy_source_id or f"patient:{patient_number}"] = item

    by_patient_number: OrderedDict[int, dict[str, Any]] = OrderedDict()
    for item in by_legacy_key.values():
        patient_number = int(item.get("patientNumber") or 0)
        by_patient_number[patient_number] = item
    return list(by_patient_number.values())


def find_existing_client_for_import(db: Session, row: dict[str, Any]) -> tuple[Client | None, str | None]:
    patient_number = row.get("patient_number")
    if patient_number:
        client = db.execute(select(Client).where(Client.patient_number == patient_number)).scalar_one_or_none()
        if client is not None:
            return client, "по № пациента"

    snils = normalize_text(row.get("snils"))
    if snils:
        client = db.execute(select(Client).where(Client.snils == snils)).scalar_one_or_none()
        if client is not None:
            return client, "по СНИЛС"

    document_series = normalize_text(row.get("document_series"))
    document_number = normalize_text(row.get("document_number"))
    if document_series and document_number:
        client = db.execute(
            select(Client).where(
                Client.document_series == document_series,
                Client.document_number == document_number,
            )
        ).scalar_one_or_none()
        if client is not None:
            return client, "по документу"

    last_name = normalize_text(row.get("last_name"))
    first_name = normalize_text(row.get("first_name"))
    middle_name = normalize_text(row.get("middle_name"))
    birth_date = row.get("birth_date")
    if last_name and first_name and birth_date:
        client = db.execute(
            select(Client).where(
                func.lower(Client.last_name) == last_name.lower(),
                func.lower(Client.first_name) == first_name.lower(),
                func.lower(func.coalesce(Client.middle_name, "")) == (middle_name or "").lower(),
                Client.birth_date == birth_date,
            )
        ).scalar_one_or_none()
        if client is not None:
            return client, "по ФИО и дате рождения"

    return None, None


def get_next_patient_number(db: Session, used_numbers: set[int]) -> int:
    patient_numbers = db.execute(select(Client.patient_number).order_by(Client.patient_number.asc())).scalars()
    expected_number = 1
    existing_numbers = set(item for item in patient_numbers if item is not None)
    existing_numbers.update(used_numbers)
    while expected_number in existing_numbers:
        expected_number += 1
    used_numbers.add(expected_number)
    return expected_number


def build_client_payload(row: dict[str, Any], patient_number: int) -> dict[str, Any]:
    registration_text = compose_registration_text(row)
    organization = normalize_text(row.get("organization"))
    return {
        "patient_number": patient_number,
        "last_name": normalize_text(row.get("last_name")) or "Без фамилии",
        "first_name": normalize_text(row.get("first_name")) or "Без имени",
        "middle_name": normalize_text(row.get("middle_name")),
        "birth_date": row["birth_date"],
        "sex": normalize_text(row.get("sex")),
        "phone": normalize_text(row.get("phone")),
        "email": normalize_text(row.get("email")),
        "document_type": normalize_text(row.get("document_type")),
        "document_series": normalize_text(row.get("document_series")),
        "document_number": normalize_text(row.get("document_number")),
        "document_issued_by": normalize_text(row.get("document_issued_by")),
        "document_issued_date": row.get("document_issued_date"),
        "snils": normalize_text(row.get("snils")),
        "registration_text": registration_text,
        "address_text": normalize_text(row.get("address_text")) or registration_text,
        "organization": organization,
        "work_place": organization,
        "profession": normalize_text(row.get("profession")),
        "indications": normalize_text(row.get("indications")),
        "flg": normalize_text(row.get("flg")),
        "admission_category": normalize_text(row.get("admission_category")),
        "reference_number": normalize_text(row.get("reference_number")),
        "notes": normalize_text(row.get("notes")),
        "legacy_payload_json": json_safe_import_row(row),
    }


def update_existing_client_from_import(client: Client, client_payload: dict[str, Any]) -> None:
    for key, value in client_payload.items():
        if value is None and key != "legacy_payload_json":
            continue
        setattr(client, key, value)


@router.post("/demo-legacy")
def import_demo_legacy(db: Session = Depends(get_db)) -> dict[str, int | str]:
    legacy_data_path = next((path for path in LEGACY_DATA_PATHS if path.exists()), None)
    if legacy_data_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Файл demo-базы не найден: {', '.join(str(path) for path in LEGACY_DATA_PATHS)}",
        )

    source = legacy_data_path.read_text(encoding="utf-8")
    try:
        clients = extract_window_json(source, "LEGACY_CLIENTS")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    import_items = dedupe_legacy_clients(clients)
    created = 0
    updated = 0
    actor_user_id = get_system_user_id(db)

    existing_by_legacy = {
        item.legacy_source_id: item
        for item in db.execute(select(Client).where(Client.legacy_source_id.is_not(None))).scalars().all()
    }
    existing_by_patient = {
        item.patient_number: item
        for item in db.execute(select(Client)).scalars().all()
    }
    existing_encounters_by_legacy = {
        item.legacy_source_id: item
        for item in db.execute(select(Encounter).where(Encounter.legacy_source_id.is_not(None))).scalars().all()
    }
    centers = db.execute(select(Center).order_by(Center.id.asc())).scalars().all()
    center_by_name = {center.name.strip().lower(): center for center in centers if center.name}
    default_center = centers[0] if centers else None

    for item in import_items:
        legacy_source_id = int(item.get("id") or 0) or None
        patient_number = int(item.get("patientNumber") or 0)
        if not patient_number:
            continue

        client = existing_by_legacy.get(legacy_source_id) if legacy_source_id is not None else None
        if client is None:
            client = existing_by_patient.get(patient_number)

        last_name, first_name, middle_name = split_full_name(item.get("fullName"))
        encounter_date = parse_optional_date(item.get("lastVisit"))
        payload = {
            "legacy_source_id": legacy_source_id,
            "patient_number": patient_number,
            "last_name": last_name,
            "first_name": first_name,
            "middle_name": middle_name,
            "birth_date": parse_date(item.get("birthDate")),
            "phone": normalize_text(item.get("phone")),
            "snils": normalize_text(item.get("snils")),
            "address_text": normalize_text(item.get("registration")),
            "registration_text": normalize_text(item.get("registration")),
            "notes": normalize_text(item.get("note")),
            "organization": normalize_text(item.get("organization")),
            "real_date_text": normalize_text(item.get("lastVisit")),
            "encounter_date_text": encounter_date.isoformat() if encounter_date is not None else normalize_text(item.get("lastVisit")),
            "legacy_payload_json": item,
        }

        if client is None:
            client = Client(created_by_user_id=actor_user_id, **payload)
            db.add(client)
            existing_by_patient[patient_number] = client
            if legacy_source_id is not None:
                existing_by_legacy[legacy_source_id] = client
            created += 1
        else:
            for key, value in payload.items():
                setattr(client, key, value)
            existing_by_patient[patient_number] = client
            if legacy_source_id is not None:
                existing_by_legacy[legacy_source_id] = client
            updated += 1

        center_name = normalize_text(item.get("center"))
        center = center_by_name.get(center_name.lower()) if center_name else None
        center = center or default_center
        if legacy_source_id is not None and encounter_date is not None and center is not None:
            db.flush()
            encounter = existing_encounters_by_legacy.get(legacy_source_id)
            if encounter is None:
                encounter = Encounter(
                    legacy_source_id=legacy_source_id,
                    center_id=center.id,
                    client_id=client.id,
                    encounter_date=encounter_date,
                    payment_type="cash",
                    total_amount=0,
                    status="completed",
                    created_by_user_id=actor_user_id,
                    comment="Imported from legacy demo data",
                )
                db.add(encounter)
                existing_encounters_by_legacy[legacy_source_id] = encounter
            else:
                encounter.center_id = center.id
                encounter.client_id = client.id
                encounter.encounter_date = encounter_date
                encounter.created_by_user_id = encounter.created_by_user_id or actor_user_id
                encounter.deleted_at = None

    db.commit()
    write_audit_log(
        db,
        entity_type="import",
        entity_id=0,
        action="demo_legacy_import",
        user_id=actor_user_id,
        payload_json={"created": created, "updated": updated, "source": str(legacy_data_path)},
    )
    db.commit()
    return {
        "source": str(legacy_data_path),
        "created": created,
        "updated": updated,
        "total": len(clients),
        "imported": len(import_items),
    }


@router.post("/clients-excel/preview", response_model=ClientImportPreviewResponse)
def preview_client_excel_import(payload: ClientImportExcelRequest, db: Session = Depends(get_db)) -> ClientImportPreviewResponse:
    try:
        rows = read_client_excel_rows(payload)
        validate_client_import_rows(rows)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    services = get_import_services(db)
    service_lookup = build_service_lookup(services)
    resolved_services: dict[int, Service | None] = {}
    try:
        for row in rows:
            resolved_services[int(row["row_number"])] = resolve_import_service(row, service_lookup, services)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    service_rows = sum(1 for service in resolved_services.values() if service is not None)
    if service_rows and get_import_center(db, get_system_user_id(db)) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для импорта услуг не найден активный медцентр",
        )
    preview_rows: list[ClientImportPreviewRow] = []
    created_candidates = 0
    update_candidates = 0

    for row in rows[:20]:
        existing_client, match_reason = find_existing_client_for_import(db, row)
        service = resolved_services[int(row["row_number"])]
        status_label = "update" if existing_client is not None else "create"
        if existing_client is not None:
            update_candidates += 1
        else:
            created_candidates += 1
        preview_rows.append(
            ClientImportPreviewRow(
                row_number=row["row_number"],
                patient_number=row.get("patient_number"),
                full_name=" ".join(
                    part for part in [row.get("last_name"), row.get("first_name"), row.get("middle_name")] if part
                ),
                birth_date=row.get("birth_date").strftime("%d.%m.%y") if row.get("birth_date") else None,
                organization=row.get("organization"),
                service_name=service.name if service is not None else None,
                encounter_date=(row.get("encounter_date") or date.today()).strftime("%d.%m.%Y")
                if service is not None
                else None,
                status=status_label,
                match_reason=match_reason,
            )
        )

    if len(rows) > 20:
        for row in rows[20:]:
            existing_client, _ = find_existing_client_for_import(db, row)
            if existing_client is not None:
                update_candidates += 1
            else:
                created_candidates += 1

    return ClientImportPreviewResponse(
        file_name=payload.file_name,
        parsed_rows=len(rows),
        created_candidates=created_candidates,
        update_candidates=update_candidates,
        service_rows=service_rows,
        preview_rows=preview_rows,
    )


@router.post("/clients-excel/commit", response_model=ClientImportResultResponse)
def commit_client_excel_import(payload: ClientImportExcelRequest, db: Session = Depends(get_db)) -> ClientImportResultResponse:
    try:
        rows = read_client_excel_rows(payload)
        validate_client_import_rows(rows)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    actor_user_id = get_system_user_id(db)
    services = get_import_services(db)
    service_lookup = build_service_lookup(services)
    visit_type_by_code = get_import_visit_types(db)
    try:
        resolved_services = {
            int(row["row_number"]): resolve_import_service(row, service_lookup, services)
            for row in rows
        }
        resolved_visit_types = {
            int(row["row_number"]): resolve_import_visit_type(row, visit_type_by_code)
            for row in rows
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    import_center = get_import_center(db, actor_user_id)
    if any(service is not None for service in resolved_services.values()) and import_center is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для импорта услуг не найден активный медцентр",
        )
    used_numbers: set[int] = set()
    created = 0
    updated = 0
    encounters_created = 0

    try:
        for row in rows:
            existing_client, _ = find_existing_client_for_import(db, row)
            patient_number = row.get("patient_number")
            if existing_client is not None:
                patient_number = existing_client.patient_number
            elif patient_number is None:
                patient_number = get_next_patient_number(db, used_numbers)
            else:
                used_numbers.add(patient_number)

            client_payload = build_client_payload(row, patient_number)

            if existing_client is None:
                client = Client(created_by_user_id=actor_user_id, **client_payload)
                db.add(client)
                created += 1
            else:
                client = existing_client
                update_existing_client_from_import(client, client_payload)
                updated += 1
            db.flush()

            service = resolved_services[int(row["row_number"])]
            if service is None:
                continue

            encounter_date = row.get("encounter_date") or date.today()
            visit_type = resolved_visit_types[int(row["row_number"])]
            encounter = Encounter(
                center_id=import_center.id,
                client_id=client.id,
                visit_type_id=visit_type.id if visit_type is not None else None,
                created_by_user_id=actor_user_id,
                encounter_date=encounter_date,
                payment_type="cash",
                total_amount=service.price,
                comment="Импортировано из Excel",
                status="draft",
            )
            db.add(encounter)
            db.flush()
            db.add(
                EncounterService(
                    encounter_id=encounter.id,
                    service_id=service.id,
                    quantity=1,
                    unit_price=service.price,
                    line_total=service.price,
                    notes="Импортировано из Excel",
                )
            )
            sync_primary_payment(db, encounter, default_comment="Импортировано из Excel")
            autofill_completed_doctors_for_service(db, encounter, service.id)
            client.encounter_date_text = encounter_date.isoformat()
            encounters_created += 1

        db.commit()
    except Exception:
        db.rollback()
        raise
    write_audit_log(
        db,
        entity_type="import",
        entity_id=0,
        action="client_excel_import",
        user_id=actor_user_id,
        payload_json={
            "file_name": payload.file_name,
            "parsed_rows": len(rows),
            "created": created,
            "updated": updated,
            "encounters_created": encounters_created,
        },
    )
    db.commit()
    return ClientImportResultResponse(
        file_name=payload.file_name,
        parsed_rows=len(rows),
        created=created,
        updated=updated,
        encounters_created=encounters_created,
    )
