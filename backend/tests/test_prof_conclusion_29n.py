import unittest

from app.services.document_generator import _health_group_mark
from app.services.new_xls_templates import LEGACY_XLS_TEMPLATE_BY_FILE


class ProfConclusion29nTests(unittest.TestCase):
    def test_health_group_keeps_only_the_numeral(self):
        """Клетка «Группа здоровья» в 29н узкая, туда влезает только номер."""
        for value, expected in [
            ("I группа здоровья", "I"),
            ("II группа здоровья", "II"),
            ("III группа здоровья, Д-наблюдение", "III"),
            ("IV группа здоровья", "IV"),
            ("V группа здоровья", "V"),
            ("I", "I"),
        ]:
            with self.subTest(value=value):
                self.assertEqual(_health_group_mark(value), expected)

    def test_health_group_longest_numeral_wins(self):
        """IV не должна усечься до I: порядок альтернатив в разборе значим."""
        self.assertEqual(_health_group_mark("IV группа здоровья"), "IV")
        self.assertEqual(_health_group_mark("III группа здоровья"), "III")

    def test_free_text_health_group_is_kept_as_is(self):
        for value in ("основная", "не установлена", "подготовительная"):
            with self.subTest(value=value):
                self.assertEqual(_health_group_mark(value), value)

    def test_empty_health_group_prints_nothing(self):
        for value in ("", "   ", None):
            with self.subTest(value=value):
                self.assertEqual(_health_group_mark(value), "")

    def test_conclusion_29n_spec_covers_the_customer_sheet(self):
        spec = LEGACY_XLS_TEMPLATE_BY_FILE["профосмотр 29н.xls"]
        self.assertEqual(spec.sheet_names, ("ПРОФОСМОТР",))
        field_ids = {field.field_id for field in spec.fields}
        for required in (
            "blank_number",
            "patient_name",
            "birth_date",
            "company",
            "position",
            "health_group",
            "chairman",
            "issue_date",
        ):
            self.assertIn(required, field_ids)


if __name__ == "__main__":
    unittest.main()
