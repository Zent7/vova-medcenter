"""Печатный агент Vova Medcenter: сам опрашивает сервер и печатает задания без диалога.

Агент работает на рабочем месте клиники, где установлены Word и Excel. Он только ходит наружу:
сообщает, что он в сети (heartbeat), забирает задание (claim), скачивает файл по временной
ссылке, печатает его и сообщает результат. Входящих подключений агент не принимает, поэтому
браузер и локальные адреса в печати не участвуют.

Настройки лежат в agent.json рядом с программой:
    {"server": "https://vova-medcenter.ravil.space", "token": "<токен агента>"}
Токен создает backend/scripts/create_print_agent.py на сервере и показывает его один раз.
Принтер для агента задается на сервере; если он не задан, печатает принтер по умолчанию.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import re
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


SUPPORTED_WORD_EXTENSIONS = {".doc", ".docx"}
SUPPORTED_EXCEL_EXTENSIONS = {".xls", ".xlsx"}
SUPPORTED_EXTENSIONS = SUPPORTED_WORD_EXTENSIONS | SUPPORTED_EXCEL_EXTENSIONS
DEFAULT_CONFIG_PATH = Path(__file__).resolve().with_name("agent.json")
HEARTBEAT_SECONDS = 20
IDLE_POLL_SECONDS = 2
ERROR_RETRY_SECONDS = 10
REPORT_ATTEMPTS = 3
HTTP_TIMEOUT_SECONDS = 20
DOWNLOAD_TIMEOUT_SECONDS = 60
MAX_COPIES = 20
TOKEN_HEADER = "X-Print-Agent-Token"
USER_AGENT = "VovaPrintAgent/2.0"
PRINT_TICKET_PATH = "/api/v1/documents/print-ticket/"

log = logging.getLogger("vova-print-agent")


class PrintAgentError(Exception):
    pass


@dataclass(frozen=True)
class AgentConfig:
    server: str
    token: str


def load_config(path: Path) -> AgentConfig:
    if not path.is_file():
        raise PrintAgentError(f"Не найден файл настроек {path}. Создайте его по образцу agent.example.json.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PrintAgentError(f"Файл настроек {path} не читается как JSON") from exc
    server = str(raw.get("server") or "").strip().rstrip("/")
    token = str(raw.get("token") or "").strip()
    parsed = urlparse(server)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
        raise PrintAgentError("В настройках server должен быть адрес сайта вида https://сервер (без пути)")
    if not token:
        raise PrintAgentError("В настройках не указан token агента")
    return AgentConfig(server=f"{parsed.scheme}://{parsed.netloc}", token=token)


def sanitize_file_name(file_name: str) -> str:
    name = Path(file_name or "document").name
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    return name or "document"


def print_file_url(config: AgentConfig, file_url: str) -> str:
    """Скачиваем только с настроенного сервера: из ссылки берем путь, сервер берем из настроек."""
    path = urlparse(file_url).path
    if not path.startswith(PRINT_TICKET_PATH):
        raise PrintAgentError("Сервер прислал ссылку, которая не похожа на файл печати")
    return f"{config.server}{path}"


class ServerClient:
    """Вызовы API печатного агента. Все запросы идут наружу, к серверу клиники."""

    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    def _post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(payload or {}).encode("utf-8")
        request = Request(
            f"{self._config.server}/api/v1/print-agent{path}",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
                TOKEN_HEADER: self._config.token,
            },
        )
        try:
            with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except HTTPError as exc:
            detail = ""
            try:
                detail = str(json.loads(exc.read().decode("utf-8")).get("detail", ""))
            except (ValueError, AttributeError):
                pass
            raise PrintAgentError(f"Сервер ответил {exc.code}: {detail or exc.reason}") from exc

    def heartbeat(self) -> dict[str, Any]:
        return self._post("/heartbeat")

    def claim(self) -> dict[str, Any] | None:
        return self._post("/jobs/claim").get("job")

    def report(self, job_id: int, *, ok: bool, error: str | None = None) -> None:
        self._post(f"/jobs/{job_id}/result", {"ok": ok, "error": error})

    def download(self, url: str, target: Path) -> None:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            target.write_bytes(response.read())


def download_path(file_name: str) -> Path:
    suffix = Path(sanitize_file_name(file_name)).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise PrintAgentError(f"Неподдерживаемый тип файла: {suffix or 'без расширения'}")
    temp_dir = Path(tempfile.gettempdir()) / "vova-print-agent"
    temp_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(sanitize_file_name(file_name)).stem
    target = temp_dir / f"{stem}{suffix}"
    counter = 1
    while target.exists():
        target = temp_dir / f"{stem}-{counter}{suffix}"
        counter += 1
    return target


def print_word_document(file_path: Path, printer_name: str | None, copies: int) -> None:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    word = None
    document = None
    previous_printer = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        if printer_name:
            previous_printer = word.ActivePrinter
            word.ActivePrinter = printer_name
        document = word.Documents.Open(
            str(file_path.resolve()),
            ReadOnly=True,
            AddToRecentFiles=False,
            Visible=False,
        )
        document.PrintOut(Background=False, Copies=copies)
    finally:
        if document is not None:
            document.Close(False)
        if word is not None:
            if previous_printer:
                try:
                    word.ActivePrinter = previous_printer
                except Exception:
                    pass
            word.Quit()
        pythoncom.CoUninitialize()


def print_excel_workbook(file_path: Path, printer_name: str | None, copies: int) -> None:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    excel = None
    workbook = None
    try:
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        workbook = excel.Workbooks.Open(str(file_path.resolve()), ReadOnly=True)
        if printer_name:
            workbook.PrintOut(Copies=copies, ActivePrinter=printer_name)
        else:
            workbook.PrintOut(Copies=copies)
    finally:
        if workbook is not None:
            workbook.Close(False)
        if excel is not None:
            excel.Quit()
        pythoncom.CoUninitialize()


def print_file(file_path: Path, printer_name: str | None, copies: int) -> None:
    suffix = file_path.suffix.lower()
    if suffix in SUPPORTED_WORD_EXTENSIONS:
        print_word_document(file_path, printer_name, copies)
        return
    if suffix in SUPPORTED_EXCEL_EXTENSIONS:
        print_excel_workbook(file_path, printer_name, copies)
        return
    raise PrintAgentError(f"Неподдерживаемый тип файла: {suffix or 'без расширения'}")


PrintFn = Callable[[Path, str | None, int], None]


def _report_with_retries(client: ServerClient, job_id: int, *, ok: bool, error: str | None = None) -> None:
    for attempt in range(1, REPORT_ATTEMPTS + 1):
        try:
            client.report(job_id, ok=ok, error=error)
            return
        except (URLError, OSError, PrintAgentError) as exc:
            log.warning("Не удалось отправить результат задания %s (попытка %s): %s", job_id, attempt, exc)
            time.sleep(ERROR_RETRY_SECONDS)
    log.error("Результат задания %s не отправлен; сервер снимет задание по таймауту", job_id)


def handle_job(
    job: dict[str, Any],
    *,
    config: AgentConfig,
    client: ServerClient,
    print_fn: PrintFn,
    dry_run: bool = False,
) -> None:
    """Печатает одно задание и сообщает результат серверу. Ошибку печати тоже отправляем на сервер."""
    job_id = int(job["id"])
    file_name = str(job.get("file_name") or "")
    copies = int(job.get("copies") or 1)
    if not 1 <= copies <= MAX_COPIES:
        copies = 1
    printer_name = str(job.get("printer_name") or "").strip() or None
    target: Path | None = None
    try:
        target = download_path(file_name)
        client.download(print_file_url(config, str(job["file_url"])), target)
        if dry_run:
            log.info("Тестовый режим: задание %s (%s) не отправлено на принтер", job_id, file_name)
        else:
            print_fn(target, printer_name, copies)
            log.info("Напечатано: задание %s, %s, копий %s", job_id, file_name, copies)
        _report_with_retries(client, job_id, ok=True)
    except Exception as exc:  # любая ошибка печати возвращается на сервер и видна сотруднику
        message = str(exc) or exc.__class__.__name__
        log.error("Задание %s не напечатано: %s", job_id, message)
        _report_with_retries(client, job_id, ok=False, error=message)
    finally:
        if target is not None:
            target.unlink(missing_ok=True)


def poll_once(
    *,
    config: AgentConfig,
    client: ServerClient,
    print_fn: PrintFn,
    dry_run: bool = False,
) -> bool:
    """Одна проверка очереди. Возвращает True, если задание было взято и обработано."""
    job = client.claim()
    if job is None:
        return False
    handle_job(job, config=config, client=client, print_fn=print_fn, dry_run=dry_run)
    return True


def run_forever(config: AgentConfig, *, dry_run: bool) -> None:
    client = ServerClient(config)
    last_heartbeat = 0.0
    log.info("Печатный агент запущен, сервер %s", config.server)
    while True:
        try:
            if time.monotonic() - last_heartbeat >= HEARTBEAT_SECONDS:
                client.heartbeat()
                last_heartbeat = time.monotonic()
            if poll_once(config=config, client=client, print_fn=print_file, dry_run=dry_run):
                continue
            time.sleep(IDLE_POLL_SECONDS)
        except (URLError, OSError, PrintAgentError) as exc:
            log.warning("Нет связи с сервером или ошибка ответа: %s", exc)
            time.sleep(ERROR_RETRY_SECONDS)


def check_connection(config: AgentConfig) -> int:
    try:
        info = ServerClient(config).heartbeat()
    except (URLError, OSError, PrintAgentError) as exc:
        print(f"Сервер не отвечает: {exc}")
        return 1
    center = info.get("center_id") or "все центры"
    print(f"Связь есть: агент «{info.get('name')}», центр {center}, принтер {info.get('printer_name') or 'по умолчанию'}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Печатный агент Vova Medcenter: тихая печать из очереди сервера")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="путь к agent.json")
    parser.add_argument("--check", action="store_true", help="проверить связь с сервером и выйти")
    parser.add_argument("--dry-run", action="store_true", help="забирать задания, но не отправлять их на принтер")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        config = load_config(args.config)
    except PrintAgentError as exc:
        print(exc)
        return 2
    if args.check:
        return check_connection(config)
    run_forever(config, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
