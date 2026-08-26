from pathlib import Path
import re

from app.core.config import settings
from app.services.new_xls_templates import LEGACY_XLS_TEMPLATE_BY_FILE, NEW_XLS_TEMPLATE_BY_FILE


SUPPORTED_TEMPLATE_EXTENSIONS = {".docx", ".xml", ".xls", ".xlsx"}
NUMBERED_LMK_TEMPLATE_FILE_NAMES = {"ЛМК.xls"}
ACTIVE_XML_TEMPLATE_NAMES = {
    "Водительская(новая).xml",
    "Чод_новый.xml",
    "ГИМС_шаблон_для_загрузки_из_файла.xml",
}
# Порядок и названия строк на странице «Шаблоны» — ровно как в списке услуг,
# который прислал заказчик. Первый блок — его список, второй — документы,
# которых в списке нет, но приложение их печатает или выгружает.
SERVICE_LIST_TEMPLATE_ORDER: tuple[tuple[str, str], ...] = (
    ("ПРОФОСМОТР 29Н.xls", "Проф"),
    ("Выписка из Амб карты (профа).xls", "Проф с выпиской"),
    ("ЛМК_справка_шаблон.docx", "ЛМК справка"),
    ("ЛМК.xls", "ЛМК-Н, ЛМК-ПР"),
    ("АМБ_карты_профосмотр_шаблон.xls", "амб карта"),
    ("CправкаБассейн_шаблон.docx", "бассейн"),
    ("СПОРТ.xls", "спорт"),
    ("Охрана_шаблон.docx", "002 (чод)"),
    ("ГИМС (судна).xls", "гимс"),
    ("трактор лиц ст.xls", "071у Лицевая"),
    ("трактор об ст.xls", "071у оборотная"),
    ("ВУ.xls", "ВУ (водительская)"),
    ("086у.жен_шаблон.docx", "086у (Ж)"),
    ("086у.муж_шаблон_2.docx", "086у (М)"),
    ("ГС НОВЫЙ ФОРМАТ.xls", "ГС"),
    ("ГТ.xls", "ГТ"),
    ("СКК 72 новый формат.xls", "072 у СКК"),
    ("СКК 070 новый формат.xls", "070у"),
    ("082у_шаблон.docx", "082у"),
    ("Справка_342н_псих_освид.xls", "342н псих осв"),
    ("095У_справка_шаблон.docx", "095у"),
)
EXTRA_TEMPLATE_ORDER: tuple[tuple[str, str], ...] = (
    ("Договор_шаблон_2.docx", "Договор"),
    ("ЭКГ_шаблон.docx", "ЭКГ"),
    ("ГТО1144_шаблон.docx", "ГТО 1144"),
    ("СЕРТ МОРСКАЯ шаблон.docx", "Морской сертификат"),
    ("Cправка_мед. осмотр_шаблон.docx", "Справка о медосмотре"),
    ("13082.docx", "13082"),
    ("13098.docx", "13098"),
    ("Водительская(новая).xml", "ВУ (водительская) — выгрузка XML"),
    ("Чод_новый.xml", "чод — выгрузка XML"),
    ("ГИМС_шаблон_для_загрузки_из_файла.xml", "гимс — выгрузка XML"),
)
TEMPLATE_ORDER: tuple[tuple[str, str], ...] = SERVICE_LIST_TEMPLATE_ORDER + EXTRA_TEMPLATE_ORDER
TEMPLATE_DISPLAY_NAMES = {file_name: name for file_name, name in TEMPLATE_ORDER}
TEMPLATE_DISPLAY_POSITION = {file_name: index for index, (file_name, _) in enumerate(TEMPLATE_ORDER)}


def template_display_position(file_name: str) -> int:
    return TEMPLATE_DISPLAY_POSITION.get(file_name, len(TEMPLATE_ORDER))


SERVICE_LIST_TEMPLATE_FILE_NAMES = frozenset(file_name for file_name, _ in SERVICE_LIST_TEMPLATE_ORDER)


def template_is_in_service_list(file_name: str) -> bool:
    """True for the blanks the customer listed; the rest stay printable but unlisted."""
    return file_name in SERVICE_LIST_TEMPLATE_FILE_NAMES


FOLDER_TEMPLATE_SOURCE_NAMES = {
    "082у_шаблон.docx": "18)082 у.docx",
    "086у.жен_шаблон.docx": "Медицинская справка 086 мед авто.docx",
    "086у.муж_шаблон_2.docx": "086 попов я.docx",
    "095У_справка_шаблон.docx": "spravka_posle_bolezni_095y (1) МЕД АВТО.doc",
    "CправкаБассейн_шаблон.docx": "20)бассейн спр.docx",
    "АМБ_карты_профосмотр_шаблон.xls": "ПРОФОСМОТР.xls",
    "ВУ.xls": "086 муж.xls; водительская лицевая.xls; водительская обратн ст.xls; ЛМК.xls",
    "Выписка из Амб карты (профа).xls": "Выписка из Амб карты (профа).xls",
    "ЛМК.xls": "ЛМК.xls",
    "ЛМК_справка_шаблон.docx": "лмк спр (3).docx",
    "ПРОФОСМОТР 29Н.xls": "ПРОФОСМОТР.xls",
    "Охрана_шаблон.docx": "ОХРАНА ВОРД.docx",
    "Справка_342н_псих_освид.xls": "псих освид.xls",
    "трактор лиц ст.xls": "Для трактора.xls",
}
ACTIVE_TEMPLATE_FILE_NAMES = frozenset(TEMPLATE_DISPLAY_NAMES)


def template_is_active_by_default(file_name: str, *, preferred_xlsx_available: bool = False) -> bool:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".xml":
        return file_name in ACTIVE_XML_TEMPLATE_NAMES
    return not preferred_xlsx_available


def get_templates_root() -> Path:
    return Path(__file__).resolve().parents[3] / "assets" / "templates" / "Templates"


def get_template_overrides_root() -> Path:
    return Path(settings.document_template_overrides_dir).resolve()


def get_template_override_path(file_name: str) -> Path:
    safe_name = Path(file_name).name
    if safe_name != file_name:
        raise ValueError("Недопустимое имя файла шаблона")
    return get_template_overrides_root() / safe_name


def template_has_override(file_name: str) -> bool:
    return get_template_override_path(file_name).is_file()


def resolve_catalog_template_path(file_name: str) -> Path:
    override_path = get_template_override_path(file_name)
    return override_path if override_path.is_file() else get_templates_root() / file_name


def template_supports_layout_editing(file_name: str) -> bool:
    normalized = file_name.casefold()
    return normalized in NEW_XLS_TEMPLATE_BY_FILE or normalized in LEGACY_XLS_TEMPLATE_BY_FILE


def slugify_template_name(value: str) -> str:
    slug = value.strip().lower()
    slug = re.sub(r"[^\w]+", "-", slug, flags=re.UNICODE)
    slug = slug.strip("-")
    return slug or "template"


def load_template_catalog() -> list[dict[str, str]]:
    root = get_templates_root()
    if not root.exists():
        return []

    paths = [
        path
        for path in sorted(
            root.iterdir(),
            key=lambda item: (template_display_position(item.name), item.name.lower()),
        )
        if (
            path.is_file()
            and path.name in ACTIVE_TEMPLATE_FILE_NAMES
            and path.suffix.lower() in SUPPORTED_TEMPLATE_EXTENSIONS
        )
    ]
    xlsx_stems = {path.stem for path in paths if path.suffix.lower() == ".xlsx"}

    catalog: list[dict[str, str]] = []
    for index, path in enumerate(paths, start=1):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_TEMPLATE_EXTENSIONS:
            continue

        source_name = FOLDER_TEMPLATE_SOURCE_NAMES.get(path.name)
        description = f"Подготовлен из папки клиента: {source_name}" if source_name else (
            f"Подключенный шаблон {path.suffix.lower().lstrip('.')}"
        )
        catalog.append(
            {
                "code": f"{slugify_template_name(path.stem)}-{index}",
                "name": TEMPLATE_DISPLAY_NAMES.get(path.name, path.stem),
                "file_name": path.name,
                "file_path": str(resolve_catalog_template_path(path.name)),
                "description": description,
                "template_type": path.suffix.lower().lstrip("."),
                "preferred_xlsx_available": path.suffix.lower() == ".xls" and path.stem in xlsx_stems,
            }
        )
    return catalog


def template_visit_type_code(template_name: str) -> str | None:
    normalized = template_name.lower()
    if "вод" in normalized or "driver" in normalized or re.search(r"(?:^|\W)ву(?:$|\W)", normalized):
        return "driver"
    if "трактор" in normalized or "tractor" in normalized or "071" in normalized:
        return "tractor"
    if "охран" in normalized or "guard" in normalized or "чод" in normalized or "002" in normalized:
        return "guard"
    if "лмк" in normalized:
        return "lmk_new"
    if "086" in normalized:
        return "086"
    if "амб" in normalized or "профосмотр" in normalized or "заключение29н" in normalized or "мед.карта" in normalized:
        return "prof"
    if "гимс" in normalized:
        return "gims"
    if "082" in normalized or "095" in normalized:
        return "other"
    if any(keyword in normalized for keyword in ("070", "072", "санатор", "морск", "marine", "seafar", "драг", "drug", "alcohol")):
        return "other"
    return None


def sync_document_template_catalog(db) -> int:
    from sqlalchemy import select

    from app.models.blank_form import (
        BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
        BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE,
        BLANK_TYPE_GUARD_MEDICAL_CERTIFICATE,
        BLANK_TYPE_LMK_MEDICAL_CERTIFICATE,
        BLANK_TYPE_TRACTOR_MEDICAL_CERTIFICATE,
    )
    from app.models.document_template import DocumentTemplate
    from app.models.visit_type import VisitType

    catalog = load_template_catalog()
    visit_type_by_code = {
        visit_type.code: visit_type
        for visit_type in db.execute(select(VisitType)).scalars().all()
    }
    existing_by_file_name = {
        template.file_name: template
        for template in db.execute(select(DocumentTemplate)).scalars().all()
    }
    existing_by_code = {
        template.code: template
        for template in existing_by_file_name.values()
    }
    target_by_file_name = {item["file_name"]: item["code"] for item in catalog}
    for file_name, target_code in target_by_file_name.items():
        template = existing_by_file_name.get(file_name)
        code_owner = existing_by_code.get(target_code)
        if template is not None and template.code != target_code:
            template.code = f"template-sync-{template.id}"
        if code_owner is not None and code_owner is not template:
            code_owner.code = f"template-sync-{code_owner.id}"
    db.flush()

    active_file_names: set[str] = set()

    for item in catalog:
        template = existing_by_file_name.get(item["file_name"])
        if template is None:
            template = DocumentTemplate(
                code=item["code"],
                name=item["name"],
                file_name=item["file_name"],
                requires_numbered_blank=False,
                blank_type=None,
            )
            db.add(template)
            existing_by_file_name[item["file_name"]] = template

        template.code = item["code"]
        template.name = item["name"]
        template.file_path = item["file_path"]
        template.description = item["description"]
        template.template_type = item["template_type"]
        template.output_format = item["template_type"]
        template.is_active = template_is_active_by_default(
            item["file_name"],
            preferred_xlsx_available=bool(item.get("preferred_xlsx_available", False)),
        )
        template.requires_numbered_blank = False
        template.blank_type = None

        haystack = " ".join([item["code"], item["name"], item["file_name"]]).lower()
        if "гимс" in haystack or "gims" in haystack:
            template.requires_numbered_blank = True
            template.blank_type = BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE
        elif item["file_name"] in NUMBERED_LMK_TEMPLATE_FILE_NAMES:
            template.requires_numbered_blank = True
            template.blank_type = BLANK_TYPE_LMK_MEDICAL_CERTIFICATE
        elif "охран" in haystack or "guard" in haystack or "чод" in haystack or "002" in haystack:
            template.requires_numbered_blank = True
            template.blank_type = BLANK_TYPE_GUARD_MEDICAL_CERTIFICATE
        elif "трактор" in haystack or "tractor" in haystack or "071" in haystack:
            template.requires_numbered_blank = True
            template.blank_type = BLANK_TYPE_TRACTOR_MEDICAL_CERTIFICATE
        elif ("вод" in haystack) or ("driver" in haystack) or re.search(r"(?:^|\W)ву(?:$|\W)", haystack):
            template.requires_numbered_blank = True
            template.blank_type = BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE

        visit_type_code = template_visit_type_code(f"{template.name} {template.file_name}")
        visit_type = visit_type_by_code.get(visit_type_code or "")
        template.visit_type_id = visit_type.id if visit_type is not None else None
        active_file_names.add(template.file_name)

    for template in existing_by_file_name.values():
        if template.file_name not in active_file_names:
            template.is_active = False

    amb_docx = existing_by_file_name.get("АМБ_карты_профосмотр_шаблон.docx")
    amb_xls = existing_by_file_name.get("АМБ_карты_профосмотр_шаблон.xls")
    amb_xlsx = existing_by_file_name.get("АМБ_карты_профосмотр_шаблон.xlsx")
    if amb_xlsx is not None:
        amb_xlsx.is_active = True
        amb_xlsx.template_type = "xlsx"
        amb_xlsx.output_format = "xlsx"
        prof_visit_type = visit_type_by_code.get("prof")
        amb_xlsx.visit_type_id = prof_visit_type.id if prof_visit_type is not None else None
    if amb_xls is not None and amb_xlsx is None:
        amb_xls.is_active = True
        amb_xls.template_type = "xls"
        amb_xls.output_format = "xls"
        prof_visit_type = visit_type_by_code.get("prof")
        amb_xls.visit_type_id = prof_visit_type.id if prof_visit_type is not None else None
    if amb_docx is not None and (amb_xls is not None or amb_xlsx is not None):
        amb_docx.is_active = False

    return len(catalog)
