from pathlib import Path
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.document_generator import _generate_docx  # noqa: E402


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def docx_text(path: Path) -> str:
    parts: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not (name.startswith("word/") and name.endswith(".xml")):
                continue
            try:
                root = ET.fromstring(archive.read(name))
            except ET.ParseError:
                continue
            parts.extend(node.text or "" for node in root.iter(f"{{{W_NS}}}t"))
    return "".join(parts)


class LmkCertificateTemplateTests(unittest.TestCase):
    def test_lmk_certificate_template_declares_ignorable_namespaces(self):
        template_path = (
            Path(__file__).resolve().parents[2]
            / "assets"
            / "templates"
            / "Templates"
            / "\u041b\u041c\u041a_\u0441\u043f\u0440\u0430\u0432\u043a\u0430_\u0448\u0430\u0431\u043b\u043e\u043d.docx"
        )
        with zipfile.ZipFile(template_path) as archive:
            xml_text = archive.read("word/document.xml").decode("utf-8")

        root_start = xml_text.index("<w:document")
        root_tag = xml_text[root_start : xml_text.index(">", root_start)]
        ignorable = re.search(r'mc:Ignorable="([^"]+)"', root_tag)
        self.assertIsNotNone(ignorable)
        for prefix in ignorable.group(1).split():
            self.assertIn(f"xmlns:{prefix}=", root_tag)

    def test_lmk_certificate_template_replaces_patient_tokens(self):
        template_path = (
            Path(__file__).resolve().parents[2]
            / "assets"
            / "templates"
            / "Templates"
            / "\u041b\u041c\u041a_\u0441\u043f\u0440\u0430\u0432\u043a\u0430_\u0448\u0430\u0431\u043b\u043e\u043d.docx"
        )
        output_path = Path(tempfile.gettempdir()) / "lmk_certificate_template_test.docx"

        _generate_docx(
            template_path,
            output_path,
            {
                "FullName": "\u0418\u0432\u0430\u043d\u043e\u0432 \u0418\u0432\u0430\u043d \u0418\u0432\u0430\u043d\u043e\u0432\u0438\u0447",
                "BirthDate": "02.01.1990",
                "AddressCalc": "\u0421\u0430\u043d\u043a\u0442-\u041f\u0435\u0442\u0435\u0440\u0431\u0443\u0440\u0433, \u041d\u0435\u0432\u0441\u043a\u0438\u0439 1",
                "Doctor": "\u041f\u0435\u0442\u0440\u043e\u0432 \u041f.\u041f.",
                "PrintDateTime": "30.06.2026 22:15",
            },
            [],
        )

        text = docx_text(output_path)

        self.assertIn("\u0418\u0432\u0430\u043d\u043e\u0432 \u0418\u0432\u0430\u043d \u0418\u0432\u0430\u043d\u043e\u0432\u0438\u0447", text)
        self.assertIn("02.01.1990", text)
        self.assertIn("\u0421\u0430\u043d\u043a\u0442-\u041f\u0435\u0442\u0435\u0440\u0431\u0443\u0440\u0433, \u041d\u0435\u0432\u0441\u043a\u0438\u0439 1", text)
        self.assertIn("\u041f\u0435\u0442\u0440\u043e\u0432 \u041f.\u041f.", text)
        self.assertIn("30.06.2026 22:15", text)
        self.assertNotRegex(text, re.compile(r"\[(FullName|BirthDate|AddressCalc|Doctor|PrintDateTime)\]"))
        self.assertNotIn("\u0413\u043e\u043c\u043e\u043d\u044e\u043a", text)
        self.assertNotIn("30.11.1990", text)
        self.assertNotIn("\u0413\u043e\u0440\u043e\u0445\u043e\u0432\u0446\u0435\u0432", text)
        self.assertNotIn("18.06.2026", text)


if __name__ == "__main__":
    unittest.main()
