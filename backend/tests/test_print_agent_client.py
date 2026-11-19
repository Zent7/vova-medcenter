"""Печатный агент рабочего места: настройки, скачивание и отчеты серверу без реального принтера.

Агент загружается из print_agent/main.py. Печать и сеть подменяются: тест проверяет, что агент
скачивает файл только с настроенного сервера, печатает нужное число копий, сообщает результат
(в том числе ошибку печати) и не оставляет временный файл.
"""

import importlib.util
import logging
import json
from pathlib import Path
import sys
import tempfile
import unittest


AGENT_PATH = Path(__file__).resolve().parents[2] / "print_agent" / "main.py"
_spec = importlib.util.spec_from_file_location("vova_print_agent_main", AGENT_PATH)
agent = importlib.util.module_from_spec(_spec)
# dataclass ищет модуль в sys.modules, поэтому регистрируем его до выполнения.
sys.modules[_spec.name] = agent
_spec.loader.exec_module(agent)

PRINT_URL = "https://vova-medcenter.ravil.space"
TICKET_PATH = "/api/v1/documents/print-ticket/token123/a.docx"


class FakeClient:
    def __init__(self) -> None:
        self.downloads: list[str] = []
        self.reports: list[tuple[int, bool, str | None]] = []
        self.next_job: dict | None = None

    def claim(self):
        job, self.next_job = self.next_job, None
        return job

    def download(self, url: str, target: Path) -> None:
        self.downloads.append(url)
        target.write_bytes(b"document")

    def report(self, job_id: int, *, ok: bool, error: str | None = None) -> None:
        self.reports.append((job_id, ok, error))


def _job(**overrides) -> dict:
    job = {
        "id": 7,
        "file_name": "a.docx",
        "copies": 2,
        "printer_name": "HP LaserJet",
        "file_url": f"http://localhost:8000{TICKET_PATH}",
    }
    job.update(overrides)
    return job


class PrintAgentConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, payload) -> Path:
        path = self.dir / "agent.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_missing_file_explains_what_to_do(self):
        with self.assertRaises(agent.PrintAgentError) as ctx:
            agent.load_config(self.dir / "absent.json")
        self.assertIn("agent.example.json", str(ctx.exception))

    def test_server_must_be_site_origin_without_path(self):
        for server in ("ftp://vova", "https://vova-medcenter.ravil.space/api", "vova-medcenter.ravil.space"):
            with self.subTest(server=server):
                path = self._write({"server": server, "token": "t"})
                with self.assertRaises(agent.PrintAgentError):
                    agent.load_config(path)

    def test_token_is_required(self):
        with self.assertRaises(agent.PrintAgentError):
            agent.load_config(self._write({"server": PRINT_URL, "token": "  "}))

    def test_valid_config_keeps_origin_only(self):
        config = agent.load_config(self._write({"server": PRINT_URL + "/", "token": "t-1"}))
        self.assertEqual(config.server, PRINT_URL)
        self.assertEqual(config.token, "t-1")


class PrintAgentDownloadTests(unittest.TestCase):
    def test_file_is_fetched_from_the_configured_server_not_from_the_link(self):
        config = agent.AgentConfig(server=PRINT_URL, token="t")
        # Сервер мог прислать внутренний адрес; агент берет только путь и идет на свой сервер.
        url = agent.print_file_url(config, "http://backend:8000" + TICKET_PATH)
        self.assertEqual(url, PRINT_URL + TICKET_PATH)

    def test_link_that_is_not_a_print_ticket_is_refused(self):
        config = agent.AgentConfig(server=PRINT_URL, token="t")
        with self.assertRaises(agent.PrintAgentError):
            agent.print_file_url(config, "https://evil.example/steal?x=1")
        with self.assertRaises(agent.PrintAgentError):
            agent.print_file_url(config, PRINT_URL + "/api/v1/clients/1")

    def test_only_office_documents_are_downloaded(self):
        with self.assertRaises(agent.PrintAgentError):
            agent.download_path("setup.exe")

    def test_file_name_is_sanitized(self):
        target = agent.download_path("../../bad name?.docx")
        self.assertEqual(target.name, "bad name_.docx")
        self.assertEqual(target.parent.name, "vova-print-agent")


class PrintAgentJobTests(unittest.TestCase):
    def setUp(self):
        self.config = agent.AgentConfig(server=PRINT_URL, token="t")
        self.client = FakeClient()
        # Ошибки печати в этих тестах ожидаемы: журнал агента не засоряем.
        logging.getLogger("vova-print-agent").setLevel(logging.CRITICAL)

    def tearDown(self):
        logging.getLogger("vova-print-agent").setLevel(logging.NOTSET)

    def test_job_is_printed_with_copies_and_printer_then_reported_ok(self):
        printed = []

        def print_fn(path, printer_name, copies):
            printed.append((path.name, printer_name, copies, path.exists()))

        agent.handle_job(_job(), config=self.config, client=self.client, print_fn=print_fn)

        self.assertEqual(self.client.downloads, [PRINT_URL + TICKET_PATH])
        self.assertEqual(printed, [("a.docx", "HP LaserJet", 2, True)])
        self.assertEqual(self.client.reports, [(7, True, None)])

    def test_temporary_file_is_removed_after_the_job(self):
        seen = []

        def print_fn(path, printer_name, copies):
            seen.append(path)

        agent.handle_job(_job(), config=self.config, client=self.client, print_fn=print_fn)
        self.assertFalse(seen[0].exists())

    def test_print_error_goes_back_to_the_server(self):
        def print_fn(path, printer_name, copies):
            raise RuntimeError("Принтер выключен")

        agent.handle_job(_job(), config=self.config, client=self.client, print_fn=print_fn)
        self.assertEqual(self.client.reports, [(7, False, "Принтер выключен")])

    def test_dry_run_does_not_print_but_still_reports(self):
        def print_fn(path, printer_name, copies):
            raise AssertionError("в тестовом режиме печать не вызывается")

        agent.handle_job(_job(), config=self.config, client=self.client, print_fn=print_fn, dry_run=True)
        self.assertEqual(self.client.reports, [(7, True, None)])

    def test_bad_copies_fall_back_to_one(self):
        printed = []

        def print_fn(path, printer_name, copies):
            printed.append(copies)

        agent.handle_job(_job(copies=99), config=self.config, client=self.client, print_fn=print_fn)
        self.assertEqual(printed, [1])

    def test_unsupported_file_is_reported_as_failed_job(self):
        def print_fn(path, printer_name, copies):
            raise AssertionError("неподдерживаемый файл не печатаем")

        agent.handle_job(_job(file_name="setup.exe"), config=self.config, client=self.client, print_fn=print_fn)
        self.assertEqual(len(self.client.reports), 1)
        self.assertFalse(self.client.reports[0][1])

    def test_poll_once_reports_whether_a_job_was_handled(self):
        printed = []

        def print_fn(path, printer_name, copies):
            printed.append(path)

        self.assertFalse(agent.poll_once(config=self.config, client=self.client, print_fn=print_fn))
        self.client.next_job = _job()
        self.assertTrue(agent.poll_once(config=self.config, client=self.client, print_fn=print_fn))
        self.assertEqual(len(printed), 1)


if __name__ == "__main__":
    unittest.main()
