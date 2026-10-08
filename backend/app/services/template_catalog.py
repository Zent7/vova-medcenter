from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import re
import shutil
import zipfile

import xlrd

from app.core.config import settings
from app.services.new_xls_templates import (
    LEGACY_XLS_TEMPLATE_BY_FILE,
    NEW_XLS_TEMPLATE_BY_FILE,
    validate_editable_xls_template,
    validate_legacy_editable_xls_template,
)


SUPPORTED_TEMPLATE_EXTENSIONS = {".docx", ".xml", ".xls", ".xlsx"}
NUMBERED_LMK_TEMPLATE_FILE_NAMES = {"ЛМК.xls"}
ACTIVE_XML_TEMPLATE_NAMES = {
    "Водительская(новая).xml",
    "Чод_новый.xml",
    "ГИМС_шаблон_для_загрузки_из_файла.xml",
}
# Порядок и названия строк на странице «Шаблоны» — ровно как в списке услуг,
# который прислал заказчик. Первый блок — его список, второй — документы,
# которых в списке нет, но приложение их печатает или выгружает. На странице
# показываем первый блок и договор: остальное заказчик не правит.
SERVICE_LIST_TEMPLATE_ORDER: tuple[tuple[str, str], ...] = (
    ("ПРОФОСМОТР 29Н.xls", "Проф"),
    ("Выписка из Амб карты (профа).xls", "Проф с выпиской"),
    ("ЛМК_справка_шаблон.docx", "ЛМК справка"),
    ("ЛМК.xls", "ЛМК-Н, ЛМК-ПР"),
    ("АМБ_карты_профосмотр_шаблон.xls", "амб карта"),
    ("CправкаБассейн_шаблон.docx", "бассейн"),
    ("СПОРТ.xls", "спорт"),
    ("ГТО_шаблон.docx", "ГТО"),
    ("ГИМС (судна).xls", "гимс"),
    ("трактор лиц ст.xls", "071у Лицевая"),
    ("трактор об ст.xls", "071у оборотная"),
    ("водительская лицевая.xls", "ВУ (водительская) лицевая"),
    ("водительская обратн ст.xls", "ВУ (водительская) оборотная"),
    ("086у.жен_шаблон.docx", "086у (Ж)"),
    ("086у.муж_шаблон_2.docx", "086у (М)"),
    # Бумажная копия СЭМД-196: бланки 086у заказчика без шапки отменённой
    # формы 086/у (приказ 834н утратил силу с 01.09.2025).
    ("СЭМД-196.жен_шаблон.docx", "СЭМД-196 (Ж)"),
    ("СЭМД-196.муж_шаблон.docx", "СЭМД-196 (М)"),
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
# Договора нет в списке услуг, но заказчик правит его сам, поэтому строка
# на странице «Шаблоны» ему нужна.
TEMPLATES_PAGE_EXTRA_FILE_NAMES = frozenset({"Договор_шаблон_2.docx"})


def template_is_in_service_list(file_name: str) -> bool:
    """True for the blanks the customer listed. Kept for app tabs opened before the last deploy."""
    return file_name in SERVICE_LIST_TEMPLATE_FILE_NAMES


def template_is_listed_on_templates_page(file_name: str) -> bool:
    """True for the blanks the customer listed plus the contract; the rest stay printable but unlisted."""
    return (
        file_name in SERVICE_LIST_TEMPLATE_FILE_NAMES
        or file_name in TEMPLATES_PAGE_EXTRA_FILE_NAMES
    )


FOLDER_TEMPLATE_SOURCE_NAMES = {
    "ГТО_шаблон.docx": "ГТО.docx",
    "082у_шаблон.docx": "18)082 у.docx",
    "086у.жен_шаблон.docx": "Медицинская справка 086 мед авто.docx",
    "086у.муж_шаблон_2.docx": "086 попов я.docx",
    "095У_справка_шаблон.docx": "spravka_posle_bolezni_095y (1) МЕД АВТО.doc",
    "CправкаБассейн_шаблон.docx": "20)бассейн спр.docx",
    "АМБ_карты_профосмотр_шаблон.xls": "ПРОФОСМОТР.xls",
    "водительская лицевая.xls": "водительская лицевая.xls",
    "водительская обратн ст.xls": "водительская обратн ст.xls",
    "Выписка из Амб карты (профа).xls": "Выписка из Амб карты (профа).xls",
    "ЛМК.xls": "ЛМК.xls",
    "ЛМК_справка_шаблон.docx": "лмк спр (3).docx",
    "ПРОФОСМОТР 29Н.xls": "ПРОФОСМОТР.xls",
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


# Клиентские версии бланков у каждого медцентра свои: в хранилище для центра
# заведена папка center-<id>, и правка в одном центре другой не затрагивает.
# Встроенные шаблоны общие: центр без своей копии печатает встроенный.
CENTER_OVERRIDE_FOLDER_PATTERN = re.compile(r"center-(\d+)")
# Сюда при старте уезжают общие клиентские версии, лежавшие в корне хранилища
# до разделения по центрам; приложение их больше не читает.
SHARED_OVERRIDES_BACKUP_FOLDER = "_shared-before-split"

logger = logging.getLogger(__name__)


def get_template_overrides_root() -> Path:
    return Path(settings.document_template_overrides_dir).resolve()


def center_override_folder_name(center_id: int) -> str:
    center_number = int(center_id)
    if center_number <= 0:
        raise ValueError("Недопустимый медцентр")
    return f"center-{center_number}"


def get_center_overrides_root(center_id: int) -> Path:
    return get_template_overrides_root() / center_override_folder_name(center_id)


def get_template_override_path(file_name: str, center_id: int) -> Path:
    safe_name = Path(file_name).name
    if safe_name != file_name:
        raise ValueError("Недопустимое имя файла шаблона")
    return get_center_overrides_root(center_id) / safe_name


def template_has_override(file_name: str, center_id: int | None) -> bool:
    """True, если у этого медцентра есть своя версия бланка."""
    if center_id is None:
        return False
    try:
        return get_template_override_path(file_name, center_id).is_file()
    except ValueError:
        return False


def center_ids_with_override_folders() -> list[int]:
    root = get_template_overrides_root()
    if not root.is_dir():
        return []
    center_ids = []
    for entry in root.iterdir():
        match = CENTER_OVERRIDE_FOLDER_PATTERN.fullmatch(entry.name)
        if match is not None and entry.is_dir():
            center_ids.append(int(match.group(1)))
    return sorted(center_ids)


def split_shared_template_overrides(center_ids) -> list[str]:
    """Разложить общие клиентские версии по папкам медцентров.

    До разделения все центры печатали одни и те же файлы из корня хранилища.
    Чтобы ничья правка не пропала, каждая такая версия копируется в папку
    каждого центра (уже лежащий там файл не трогаем), а оригинал уходит в
    ``SHARED_OVERRIDES_BACKUP_FOLDER``. Файл, который не удалось скопировать,
    остаётся на месте до следующего старта. Возвращает имена разложенных файлов.
    """
    target_ids = sorted({int(center_id) for center_id in center_ids})
    root = get_template_overrides_root()
    if not target_ids or not root.is_dir():
        return []

    shared_files = [entry for entry in sorted(root.iterdir()) if entry.is_file()]
    if not shared_files:
        return []

    backup_root = root / SHARED_OVERRIDES_BACKUP_FOLDER
    split_names: list[str] = []
    for source in shared_files:
        try:
            if source.suffix.lower() in SUPPORTED_TEMPLATE_EXTENSIONS:
                for center_id in target_ids:
                    target = get_template_override_path(source.name, center_id)
                    if target.exists():
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    partial = target.with_name(f"{target.name}.splitting")
                    shutil.copy2(source, partial)
                    partial.replace(target)
            backup_root.mkdir(parents=True, exist_ok=True)
            backup = backup_root / source.name
            if backup.exists():
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                backup = backup_root / f"{source.name}.{stamp}"
            source.replace(backup)
            split_names.append(source.name)
        except OSError:
            logger.exception("Не удалось разложить общий шаблон %s по медцентрам", source.name)
    return split_names


# Бланки, которые заказчик уже переоформил под конкретный центр (реквизиты в
# шапках, договор), лежат в репозитории: Centers/<код центра>/<файл>. Это
# начальная клиентская версия центра. При старте она копируется в папку центра
# center-<id>, и центр печатает её, а не общий встроенный бланк.
CENTER_DEFAULTS_FOLDER = "Centers"
# Что из набора уже разложено в папку центра (имя файла -> хэш разложенной
# копии, null — у центра уже была своя). Без этого «Вернуть исходный» или
# удалённый вручную файл оживал бы при следующем старте.
CENTER_DEFAULTS_MARKER = ".seeded-defaults.json"


def get_center_defaults_root(center_code: str) -> Path:
    return get_templates_root().parent / CENTER_DEFAULTS_FOLDER / center_code


def center_default_template_path(center_code: str, file_name: str) -> Path | None:
    """Файл из начального набора центра или None, если для него набора нет."""
    if Path(center_code).name != center_code or Path(file_name).name != file_name:
        return None
    path = get_center_defaults_root(center_code) / file_name
    return path if path.is_file() else None


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_into_place(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f"{target.name}.seeding")
    shutil.copy2(source, partial)
    partial.replace(target)


def _is_untouched_split_copy(target: Path) -> bool:
    """True, если файл центра — нетронутая копия общей версии, разложенной при разделении.

    Оригиналы общих версий лежат в ``SHARED_OVERRIDES_BACKUP_FOLDER`` (рядом
    могут быть и копии со штампом времени). Совпадение байт с оригиналом значит,
    что центр свою правку не загружал: бланк ему достался от другого центра.
    """
    backup_root = get_template_overrides_root() / SHARED_OVERRIDES_BACKUP_FOLDER
    if not backup_root.is_dir():
        return False
    try:
        digest = _file_digest(target)
        for backup in backup_root.iterdir():
            if backup.is_file() and (backup.name == target.name or backup.name.startswith(f"{target.name}.")):
                if _file_digest(backup) == digest:
                    return True
    except OSError:
        return False
    return False


def _read_seeded_defaults(center_dir: Path) -> dict[str, str | None]:
    try:
        data = json.loads((center_dir / CENTER_DEFAULTS_MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_seeded_defaults(center_dir: Path, seeded: dict[str, str | None]) -> None:
    center_dir.mkdir(parents=True, exist_ok=True)
    marker = center_dir / CENTER_DEFAULTS_MARKER
    partial = marker.with_name(f"{marker.name}.writing")
    partial.write_text(json.dumps(seeded, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    partial.replace(marker)


def seed_center_template_defaults(centers) -> list[str]:
    """Разложить начальные наборы бланков по папкам центров.

    ``centers`` — пары (id, код). Файл из ``Centers/<код>`` копируется в папку
    центра один раз: если у центра уже есть своя копия, она остаётся нетронутой,
    а удалённый после этого файл не возвращается. Копия, которую заказчик не
    правил, подтягивает новую версию набора, когда набор в репозитории
    поменялся. Исключение — копия, разошедшаяся по центрам при разделении общих
    версий (``split_shared_template_overrides``) и с тех пор не менявшаяся: это
    чужой бланк, а не правка центра, набор её заменяет. Возвращает записи
    «id/файл» разложенных или обновлённых файлов.
    """
    placed: list[str] = []
    for center_id, center_code in centers:
        if Path(center_code).name != center_code:
            continue
        defaults_root = get_center_defaults_root(center_code)
        if not defaults_root.is_dir():
            continue
        center_dir = get_center_overrides_root(center_id)
        seeded = _read_seeded_defaults(center_dir)
        changed = False
        for source in sorted(defaults_root.iterdir()):
            if not source.is_file() or source.suffix.lower() not in SUPPORTED_TEMPLATE_EXTENSIONS:
                continue
            try:
                target = get_template_override_path(source.name, center_id)
                source_digest = _file_digest(source)
                if source.name not in seeded:
                    if target.exists() and not _is_untouched_split_copy(target):
                        seeded[source.name] = None
                    else:
                        _copy_into_place(source, target)
                        seeded[source.name] = source_digest
                        placed.append(f"{center_id}/{source.name}")
                    changed = True
                elif (
                    seeded[source.name] not in (None, source_digest)
                    and target.is_file()
                    and _file_digest(target) == seeded[source.name]
                ):
                    _copy_into_place(source, target)
                    seeded[source.name] = source_digest
                    placed.append(f"{center_id}/{source.name}")
                    changed = True
            except (OSError, ValueError):
                logger.exception("Не удалось разложить бланк %s центру %s", source.name, center_code)
        if changed:
            try:
                _write_seeded_defaults(center_dir, seeded)
            except OSError:
                logger.exception("Не удалось записать, что набор бланков центра %s разложен", center_code)
    return placed


def restore_center_template_default(center_id: int, center_code: str, file_name: str) -> bool:
    """Вернуть центру его начальную версию бланка. False — набора для файла нет."""
    default_path = center_default_template_path(center_code, file_name)
    if default_path is None:
        return False
    target = get_template_override_path(file_name, center_id)
    _copy_into_place(default_path, target)
    center_dir = get_center_overrides_root(center_id)
    seeded = _read_seeded_defaults(center_dir)
    seeded[file_name] = _file_digest(default_path)
    _write_seeded_defaults(center_dir, seeded)
    return True


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _repair_mojibake(value: str) -> str:
    try:
        return value.encode("latin1").decode("utf-8")
    except UnicodeError:
        return value


def resolve_template_file(template, center_id: int | None = None) -> Path | None:
    """Файл, который и отдаёт страница «Шаблоны», и заполняет печать.

    Клиентская версия медцентра из его папки перекрывает встроенную; без
    ``center_id`` берётся встроенная. Путь из базы — лишь запасной: его
    запоминает синхронизация каталога, и он может отстать от хранилища. Путь
    внутри хранилища правок (так лежала общая версия до разделения по
    центрам) не берём: чужая копия не должна попасть в печать. Печать и
    скачивание берут файл только отсюда, чтобы в услуге не оказалось другого
    бланка, чем тот, что заказчик правил.
    """
    candidates: list[Path] = []
    if center_id is not None:
        try:
            candidates.append(get_template_override_path(template.file_name, center_id))
        except ValueError:
            pass
    if template.file_path:
        cached_path = Path(template.file_path)
        if not _is_inside(cached_path, get_template_overrides_root()):
            candidates.append(cached_path)

    root = get_templates_root()
    names = [template.file_name]
    repaired_name = _repair_mojibake(template.file_name)
    if repaired_name != template.file_name:
        names.append(repaired_name)

    for name in names:
        if name:
            candidates.append(root / name)

    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
    return None


# Клиентская версия шаблона лежит в хранилище и перекрывает встроенную, а
# деплой хранилище не трогает: правка бланка в коде до печати не доходит, пока
# кто-нибудь не нажмёт «Вернуть исходный». Устаревшую версию снимаем сами:
# Word-бланк из этого списка — пока в нём нет метки, ради которой его
# переделывали, а Excel-бланк со свободным макетом — когда в нём не хватает
# метки поля, добавленного во встроенный шаблон. Такую версию печать
# заполнить не может, а подменять её встроенной нельзя: тогда на странице
# «Шаблоны» лежал бы один бланк, а в услуге печатался другой.
OUTDATED_TEMPLATE_OVERRIDE_TOKENS = {
    # Справка 095у получила из карточки председателя «школу / дошкольное
    # учреждение», статус обучающегося и контакт с инфекционными больными.
    "095У_справка_шаблон.docx": "[Certificate095InstitutionKind]",
    # Справка ГТО получила строки спортсмена, «допущен к…» и ограничений: без них
    # поля карточки председателя в справку не попадают.
    "ГТО_шаблон.docx": "[GtoAthleteRegistryNumber]",
}


def docx_text_contains(path: Path, token: str) -> bool:
    """True, если в тексте .docx есть метка — даже разрезанная Word на куски."""
    with zipfile.ZipFile(path) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    return token in re.sub(r"<[^>]+>", "", document_xml)


def xls_override_misses_current_fields(file_name: str, path: Path) -> bool:
    """True, если клиентская XLS-версия не проходит проверку текущих меток полей."""
    spec = NEW_XLS_TEMPLATE_BY_FILE.get(file_name.casefold())
    legacy_spec = LEGACY_XLS_TEMPLATE_BY_FILE.get(file_name.casefold())
    if spec is None and legacy_spec is None:
        return False
    try:
        xlrd.open_workbook(file_contents=path.read_bytes(), formatting_info=True)
    except Exception:
        # Нечитаемый файл не трогаем: печать сама сообщит, что с ним не так.
        return False
    try:
        if spec is not None:
            validate_editable_xls_template(path, spec)
        else:
            validate_legacy_editable_xls_template(path, legacy_spec)
    except ValueError:
        return True
    return False


def _override_is_outdated(file_name: str, override_path: Path) -> bool:
    required_token = OUTDATED_TEMPLATE_OVERRIDE_TOKENS.get(file_name)
    if required_token is not None:
        return not docx_text_contains(override_path, required_token)
    return xls_override_misses_current_fields(file_name, override_path)


def _retirable_override_file_names() -> tuple[str, ...]:
    xls_file_names = sorted(
        {spec.file_name for spec in NEW_XLS_TEMPLATE_BY_FILE.values()}
        | {spec.file_name for spec in LEGACY_XLS_TEMPLATE_BY_FILE.values()}
    )
    return (*OUTDATED_TEMPLATE_OVERRIDE_TOKENS, *xls_file_names)


def retire_outdated_template_overrides() -> None:
    """Отложить клиентские версии бланков, в которых нет новых меток полей."""
    for center_id in center_ids_with_override_folders():
        for file_name in _retirable_override_file_names():
            try:
                override_path = get_template_override_path(file_name, center_id)
            except ValueError:
                continue
            if not override_path.is_file() or not (get_templates_root() / file_name).is_file():
                continue
            try:
                if not _override_is_outdated(file_name, override_path):
                    continue
                # Файл не удаляем: заказчик правил его сам, и по имени с суффиксом
                # приложение его уже не подхватит, а вернуть версию можно вручную.
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                override_path.rename(override_path.with_name(f"{override_path.name}.retired-{stamp}"))
            except (OSError, KeyError, ValueError, zipfile.BadZipFile, UnicodeDecodeError):
                continue


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
                # Путь в базе всегда встроенный: клиентские версии у центров свои,
                # их ищет resolve_template_file по центру.
                "file_path": str(path),
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
    if "086" in normalized or "сэмд" in normalized:
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
