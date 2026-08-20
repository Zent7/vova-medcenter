from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

from fastapi import HTTPException


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.v1.routes import documents  # noqa: E402


class DummyRequest:
    def __init__(self, url: str, host: str):
        self.url = url
        self.headers = {"host": host}

    def url_for(self, route_name, **path_params):
        return self.url


class DocumentPrintTicketTests(unittest.TestCase):
    def setUp(self):
        documents._print_tickets.clear()

    def tearDown(self):
        documents._print_tickets.clear()

    def test_print_ticket_can_be_downloaded_more_than_once_before_expiry(self):
        token = "word-metadata-probe"
        file_path = Path(__file__).resolve()
        documents._print_tickets[token] = (file_path, datetime.now(timezone.utc) + timedelta(minutes=1))

        first_response = documents._download_print_ticket(token)
        second_response = documents._download_print_ticket(token)

        self.assertEqual(Path(first_response.path), file_path)
        self.assertEqual(Path(second_response.path), file_path)

    def test_expired_print_ticket_is_removed(self):
        token = "expired"
        file_path = Path(__file__).resolve()
        documents._print_tickets[token] = (file_path, datetime.now(timezone.utc) - timedelta(seconds=1))

        with self.assertRaises(HTTPException):
            documents._download_print_ticket(token)

        self.assertNotIn(token, documents._print_tickets)

    def test_public_ticket_url_uses_configured_https_origin(self):
        original_origin = documents.settings.public_frontend_origin
        documents.settings.public_frontend_origin = "https://vova-medcenter.ravil.space"
        file_name = "C\u043f\u0440\u0430\u0432\u043a\u0430_\u043c\u0435\u0434. \u043e\u0441\u043c\u043e\u0442\u0440_\u0448\u0430\u0431\u043b\u043e\u043d.docx"
        request = DummyRequest(
            f"http://vova-medcenter.ravil.space/api/v1/documents/print-ticket/token/{file_name}",
            "vova-medcenter.ravil.space",
        )

        try:
            public_url = documents._public_url_for(
                request,
                "download_print_ticket_file_named",
                token="token",
                file_name=file_name,
            )
        finally:
            documents.settings.public_frontend_origin = original_origin

        self.assertEqual(
            public_url,
            "https://vova-medcenter.ravil.space/api/v1/documents/print-ticket/token/"
            "C%D0%BF%D1%80%D0%B0%D0%B2%D0%BA%D0%B0_%D0%BC%D0%B5%D0%B4.%20"
            "%D0%BE%D1%81%D0%BC%D0%BE%D1%82%D1%80_%D1%88%D0%B0%D0%B1%D0%BB%D0%BE%D0%BD.docx",
        )

    def test_local_ticket_url_keeps_request_origin(self):
        original_origin = documents.settings.public_frontend_origin
        documents.settings.public_frontend_origin = "https://vova-medcenter.ravil.space"
        request = DummyRequest("http://localhost:8000/api/v1/documents/print-ticket/token/file.docx", "localhost:8000")

        try:
            public_url = documents._public_url_for(
                request,
                "download_print_ticket_file_named",
                token="token",
                file_name="file.docx",
            )
        finally:
            documents.settings.public_frontend_origin = original_origin

        self.assertEqual(public_url, "http://localhost:8000/api/v1/documents/print-ticket/token/file.docx")


if __name__ == "__main__":
    unittest.main()
