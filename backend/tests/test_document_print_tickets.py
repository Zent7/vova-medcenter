from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

from fastapi import HTTPException


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.v1.routes import documents  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
