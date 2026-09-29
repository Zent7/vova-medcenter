"""Значения из карточек подставляются в разметку Word и не должны её ломать.

Текст, набранный оператором или врачом (название мероприятия, ограничения),
попадает в document.xml как есть. Раньше `&` и `<` в нём давали документ, который
Word не открывает, а обратный слэш строка замены читала как ссылку на группу.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import document_generator as generator  # noqa: E402


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def generated_text(body: str, context: dict[str, str]) -> str:
    """Текст документа, собранного из шаблона с одним набором абзацев.

    Разбор document.xml падает, если генератор оставил в разметке сырой `&` или `<`.
    """
    with tempfile.TemporaryDirectory() as directory:
        template = Path(directory) / "template.docx"
        with zipfile.ZipFile(template, "w") as archive:
            archive.writestr(
                "word/document.xml",
                f'<w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>',
            )
        output = Path(directory) / "output.docx"
        generator._generate_docx(template, output, context)
        with zipfile.ZipFile(output) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
    return "".join(root.itertext())


class DocxTokenEscapingTests(unittest.TestCase):
    def test_ampersand_and_angle_brackets_are_printed_as_text(self):
        text = generated_text(
            "<w:p><w:r><w:t>Мероприятие: [EventName]</w:t></w:r></w:p>",
            {"EventName": "Кубок Р&К <финал>"},
        )
        self.assertEqual(text, "Мероприятие: Кубок Р&К <финал>")

    def test_backslash_is_not_read_as_a_group_reference(self):
        text = generated_text(
            "<w:p><w:r><w:t>[EventName]</w:t></w:r></w:p>",
            {"EventName": "путь\\1 и \\g<0>"},
        )
        self.assertEqual(text, "путь\\1 и \\g<0>")

    def test_token_split_inside_its_name_keeps_special_characters(self):
        """Word режет метку посреди имени, и её заменяет уже проход по дереву."""
        text = generated_text(
            "<w:p><w:r><w:t>[Event</w:t></w:r><w:r><w:t>Name]</w:t></w:r></w:p>",
            {"EventName": "Р&К <финал> \\1"},
        )
        self.assertEqual(text, "Р&К <финал> \\1")

    def test_token_split_into_brackets_and_name_keeps_special_characters(self):
        text = generated_text(
            "<w:p><w:r><w:t>[</w:t></w:r><w:r><w:t>EventName</w:t></w:r><w:r><w:t>]</w:t></w:r></w:p>",
            {"EventName": "Р&К <финал> \\1"},
        )
        self.assertEqual(text, "Р&К <финал> \\1")

    def test_plain_values_are_unchanged(self):
        text = generated_text(
            "<w:p><w:r><w:t>[|LastName|] [FirstName]</w:t></w:r></w:p>",
            {"LastName": "Иванов", "FirstName": 'Иван "Ваня"'},
        )
        self.assertEqual(text, 'Иванов Иван "Ваня"')


if __name__ == "__main__":
    unittest.main()
