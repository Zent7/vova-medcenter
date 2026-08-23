from datetime import date
from pathlib import Path
from types import SimpleNamespace
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.base import Base  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.generated_document import GeneratedDocument  # noqa: E402
from app.services.document_generator import (  # noqa: E402
    _generate_docx,
    _is_lmk_certificate_template,
    _lock_sequential_document_numbers,
    _next_sequential_document_number,
)


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


LMK_CERTIFICATE_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "templates"
    / "Templates"
    / "ЛМК_справка_шаблон.docx"
)


class LmkCertificateNumberTests(unittest.TestCase):
    """Справка ЛМК печатается на чистом А4 с порядковым номером."""

    TEMPLATE_ID = 7

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _add_client(self, db, patient_number):
        client = Client(
            patient_number=patient_number,
            last_name="Иванов",
            first_name="Иван",
            birth_date=date(1990, 1, 2),
        )
        db.add(client)
        db.flush()
        return client

    def _add_document(self, db, *, client_id, encounter_id, number):
        document = GeneratedDocument(
            client_id=client_id,
            encounter_id=encounter_id,
            template_id=self.TEMPLATE_ID,
            document_number=number,
            file_name=f"lmk-{number}.docx",
            file_path=f"/tmp/lmk-{number}.docx",
            generated_by_user_id=1,
        )
        db.add(document)
        db.flush()
        return document

    def test_template_prints_certificate_number(self):
        output_path = Path(tempfile.gettempdir()) / "lmk_certificate_number_test.docx"
        _generate_docx(LMK_CERTIFICATE_TEMPLATE_PATH, output_path, {"CertificateNumber": "17"}, [])

        text = docx_text(output_path)
        self.assertIn("Справка № 17", text)
        self.assertNotIn("[CertificateNumber]", text)

    def test_certificate_template_is_detected_by_file_name(self):
        self.assertTrue(
            _is_lmk_certificate_template(
                SimpleNamespace(
                    file_name="ЛМК_справка_шаблон.docx",
                    file_path=None,
                )
            )
        )
        self.assertFalse(
            _is_lmk_certificate_template(SimpleNamespace(file_name="ЛМК.xls", file_path=None))
        )

    def test_numbering_starts_at_one_and_increments(self):
        with self.Session() as db:
            client = self._add_client(db, 1)
            self.assertEqual(
                _next_sequential_document_number(
                    db, template_id=self.TEMPLATE_ID, client_id=client.id, encounter_id=1
                ),
                "1",
            )
            self._add_document(db, client_id=client.id, encounter_id=1, number="1")
            self.assertEqual(
                _next_sequential_document_number(
                    db, template_id=self.TEMPLATE_ID, client_id=client.id, encounter_id=2
                ),
                "2",
            )

    def test_reprint_of_same_encounter_reuses_number(self):
        with self.Session() as db:
            client = self._add_client(db, 2)
            self._add_document(db, client_id=client.id, encounter_id=11, number="5")
            self.assertEqual(
                _next_sequential_document_number(
                    db, template_id=self.TEMPLATE_ID, client_id=client.id, encounter_id=11
                ),
                "5",
            )

    def test_non_numeric_legacy_numbers_are_ignored(self):
        with self.Session() as db:
            client = self._add_client(db, 3)
            self._add_document(
                db, client_id=client.id, encounter_id=21, number="ЛМК 900001"
            )
            self.assertEqual(
                _next_sequential_document_number(
                    db, template_id=self.TEMPLATE_ID, client_id=client.id, encounter_id=22
                ),
                "1",
            )


class SequentialNumberLockTests(unittest.TestCase):
    """Номер выдаётся как max+1 задолго до вставки строки — его надо сериализовать."""

    class _Dialect:
        def __init__(self, name):
            self.name = name

    class _Bind:
        def __init__(self, name):
            self.dialect = SequentialNumberLockTests._Dialect(name)

    class _Session:
        def __init__(self, dialect_name):
            self._bind = SequentialNumberLockTests._Bind(dialect_name)
            self.statements = []

        def get_bind(self):
            return self._bind

        def execute(self, statement, params=None):
            self.statements.append((str(statement), params))
            return None

    def test_postgresql_takes_an_advisory_transaction_lock(self):
        session = self._Session("postgresql")
        _lock_sequential_document_numbers(session, 7)

        self.assertEqual(len(session.statements), 1)
        statement, params = session.statements[0]
        self.assertIn("pg_advisory_xact_lock", statement)
        self.assertEqual(params["template_id"], 7)

    def test_other_dialects_are_skipped(self):
        session = self._Session("sqlite")
        _lock_sequential_document_numbers(session, 7)

        self.assertEqual(session.statements, [])


if __name__ == "__main__":
    unittest.main()
