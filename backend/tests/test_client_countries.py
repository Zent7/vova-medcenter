from datetime import date
from pathlib import Path
import sys
import unittest

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.api.v1.routes.clients import normalize_payload
from app.schemas.client import ClientCreate, ClientUpdate


class ClientCountriesTests(unittest.TestCase):
    def payload(self):
        return dict(last_name="Проверкин", first_name="Иван", birth_date=date(1990, 1, 1))

    def test_country_fields_are_normalized_separately(self):
        data = normalize_payload(ClientCreate(**self.payload(), citizenship=" Армения ", arrival_country=" Грузия "))
        self.assertEqual((data["citizenship"], data["arrival_country"]), ("Армения", "Грузия"))

    def test_older_client_update_preserves_countries(self):
        data = normalize_payload(ClientUpdate(**self.payload(), phone="123"))
        self.assertNotIn("citizenship", data)
        self.assertNotIn("arrival_country", data)

    def test_explicit_empty_values_clear_countries(self):
        data = normalize_payload(ClientUpdate(**self.payload(), citizenship=" ", arrival_country=None))
        self.assertIsNone(data["citizenship"])
        self.assertIsNone(data["arrival_country"])

    def test_country_length_is_validated_before_database_write(self):
        with self.assertRaises(ValidationError):
            ClientCreate(**self.payload(), citizenship="x" * 256)
