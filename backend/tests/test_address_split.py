import json
import unittest
from pathlib import Path

from app.services.document_context import _split_address


CASES = json.loads((Path(__file__).parent / "fixtures" / "address_cases.json").read_text(encoding="utf-8"))


class SplitAddressTests(unittest.TestCase):
    """Тот же список случаев проверяет parseClientAddressSuggestion в client-modal.js."""

    def test_cases_file_is_not_empty(self):
        self.assertGreaterEqual(len(CASES), 10)

    def test_every_case_splits_into_the_expected_parts(self):
        for case in CASES:
            with self.subTest(case["name"]):
                self.assertEqual(_split_address(case["address"]), case["expected"])

    def test_missing_district_does_not_shift_the_street_into_the_city(self):
        parts = _split_address("Россия, Санкт-Петербург, Санкт-Петербург, пр. Невский, д. 10, кв. 5")
        self.assertEqual(parts["city"], "Санкт-Петербург")
        self.assertEqual(parts["street"], "пр. Невский")
        self.assertEqual(parts["house"], "10")

    def test_flat_stays_a_flat_when_the_building_is_empty(self):
        parts = _split_address("Россия, Ленинградская область, Всеволожский район, Мурино, Центральная, 10, 5")
        self.assertEqual((parts["house"], parts["body"], parts["apartment"]), ("10", "", "5"))

    def test_street_types_from_the_customer_list_are_recognized(self):
        for street in ("ул. Кирова", "улица Кирова", "пр. Кирова", "пр-кт Кирова", "проспект Кирова", "проезд Кирова", "бул. Кирова", "бульвар Кирова"):
            with self.subTest(street):
                parts = _split_address(f"Ленинградская обл., г. Гатчина, {street}, д. 4")
                self.assertEqual(parts["street"], street)

    def test_address_built_like_the_client_card_is_split_back_for_any_empty_part(self):
        """Карточка склеивает непустые части с приставками (client-modal.js); печать разбирает обратно."""
        regions = [
            ("Санкт-Петербург", "Санкт-Петербург", [""]),
            ("Ленинградская область", "Мурино", ["", "Всеволожский район"]),
        ]
        checked = 0
        for subject, city, districts in regions:
            for district in districts:
                for street_type in ("", "пр.", "проезд"):
                    for building in ("", "2"):
                        for flat in ("", "5"):
                            street = f"{street_type} Невский".strip()
                            text = ", ".join(
                                part
                                for part in (
                                    "Россия",
                                    subject,
                                    district,
                                    city,
                                    street,
                                    "д. 10",
                                    f"корп. {building}" if building else "",
                                    f"кв. {flat}" if flat else "",
                                )
                                if part
                            )
                            with self.subTest(text):
                                self.assertEqual(
                                    _split_address(text),
                                    {
                                        "subject": subject,
                                        "district": district,
                                        "city": city,
                                        "street": street,
                                        "house": "10",
                                        "body": building,
                                        "apartment": flat,
                                    },
                                )
                                checked += 1
        self.assertEqual(checked, 36)

    def test_plain_addresses_without_country_are_parsed_as_before(self):
        parts = _split_address("г. Санкт-Петербург, Невский проспект, д. 10, корп. 2, кв. 15")
        self.assertEqual(parts["street"], "Невский проспект")
        self.assertEqual((parts["house"], parts["body"], parts["apartment"]), ("10", "2", "15"))


if __name__ == "__main__":
    unittest.main()
