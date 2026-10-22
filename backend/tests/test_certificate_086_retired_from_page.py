import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.template_catalog import (  # noqa: E402
    TEMPLATE_DISPLAY_NAMES,
    template_is_listed_on_templates_page,
)

CERTIFICATE_086_FILES = ("086у.жен_шаблон.docx", "086у.муж_шаблон_2.docx")


class Certificate086RetiredFromPageTests(unittest.TestCase):
    """Справка 086у заменена СЭМД-196: строк на странице «Шаблоны» нет, печать старых справок работает."""

    def test_the_086_blanks_are_not_listed_on_the_templates_page(self):
        for file_name in CERTIFICATE_086_FILES:
            with self.subTest(file_name=file_name):
                self.assertFalse(template_is_listed_on_templates_page(file_name))

    def test_the_086_blanks_stay_known_for_printing(self):
        self.assertEqual(TEMPLATE_DISPLAY_NAMES["086у.жен_шаблон.docx"], "086у (Ж)")
        self.assertEqual(TEMPLATE_DISPLAY_NAMES["086у.муж_шаблон_2.docx"], "086у (М)")


if __name__ == "__main__":
    unittest.main()
