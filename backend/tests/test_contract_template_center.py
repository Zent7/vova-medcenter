"""Договор клиента из нескольких центров печатается шаблоном нужного центра.

У каждого центра свои клиентские версии шаблонов. Клиент, заведённый в два
центра, получает два разных договора («Договор Мед-Авто» и «Договор Медилэнд»),
поэтому печать может назвать центр, чей шаблон взять; без названия берётся
центр обращения.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch
import zipfile

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


os.environ.setdefault("ALLOW_SQLITE", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.document_template import DocumentTemplate  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.models.encounter_service import EncounterService  # noqa: E402
from app.models.service import Service  # noqa: E402
from app.schemas.document_generation import DocumentGenerateRequest as GenerateRequestSchema  # noqa: E402
from app.services import document_generator  # noqa: E402
from app.services.template_catalog import get_template_override_path  # noqa: E402


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_TEMPLATE_PATH = next(
    path
    for path in (REPOSITORY_ROOT / "assets" / "templates").rglob("*.docx")
    if path.stem.lower() == "договор_шаблон_2"
)
MEDILAND_MARKER = "ДОГОВОР-МЕДИЛЭНД-ОСОБЫЙ"


def contract_with_marker(source: Path, target: Path, marker: str) -> None:
    """Копия договора с лишней строкой: так видно, чей именно файл напечатан."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as copy:
        for item in original.infolist():
            content = original.read(item.filename)
            if item.filename == "word/document.xml":
                xml_text = content.decode("utf-8")
                paragraph = f"<w:p><w:r><w:t>{marker}</w:t></w:r></w:p>"
                xml_text = xml_text.replace("</w:body>", paragraph + "</w:body>", 1)
                content = xml_text.encode("utf-8")
            copy.writestr(item, content)


class ContractTemplateCenterTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.output_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.output_dir.cleanup)
        self.overrides_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.overrides_dir.cleanup)
        original_overrides_dir = settings.document_template_overrides_dir
        settings.document_template_overrides_dir = self.overrides_dir.name
        self.addCleanup(setattr, settings, "document_template_overrides_dir", original_overrides_dir)

        self.db.add_all(
            [
                Center(id=1, code="center-a", name="Мед-Авто"),
                Center(id=2, code="center-b", name="Медилэнд"),
            ]
        )
        self.client = Client(
            id=1, patient_number=1, last_name="Тестов", first_name="Тест", birth_date=date(1990, 1, 1)
        )
        self.service = Service(id=1, code="service-1", name="Медицинская комиссия", price=Decimal("1000.00"))
        self.template = DocumentTemplate(
            id=1,
            code="contract",
            name="Договор на оказание платных медицинских услуг",
            file_name=CONTRACT_TEMPLATE_PATH.name,
            file_path=str(CONTRACT_TEMPLATE_PATH),
            template_type="docx",
        )
        self.db.add_all([self.client, self.service, self.template])
        self.db.flush()
        # Обращение клиента оформлено в Мед-Авто.
        self.encounter = Encounter(
            center_id=1,
            client_id=self.client.id,
            encounter_date=date(2026, 10, 7),
            payment_type="cash",
            total_amount=Decimal("1000.00"),
        )
        self.db.add(self.encounter)
        self.db.flush()
        self.db.add(
            EncounterService(
                encounter_id=self.encounter.id,
                service_id=self.service.id,
                quantity=1,
                unit_price=Decimal("1000.00"),
                line_total=Decimal("1000.00"),
            )
        )
        self.db.commit()
        # Свой договор есть только у Медилэнда.
        contract_with_marker(
            CONTRACT_TEMPLATE_PATH,
            get_template_override_path(CONTRACT_TEMPLATE_PATH.name, 2),
            MEDILAND_MARKER,
        )

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def contract_text(self, **extra) -> str:
        with patch.object(document_generator.settings, "generated_documents_dir", self.output_dir.name):
            result = document_generator.generate_document(
                self.db,
                template_id=self.template.id,
                template_code=None,
                client_id=self.client.id,
                encounter_id=self.encounter.id,
                **extra,
            )
        with zipfile.ZipFile(result.output_file_path) as archive:
            return re.sub(r"<[^>]+>", "", archive.read("word/document.xml").decode("utf-8"))

    def test_without_a_named_center_the_encounter_center_template_is_used(self):
        self.assertNotIn(MEDILAND_MARKER, self.contract_text())

    def test_the_other_center_contract_is_printed_for_the_same_encounter(self):
        self.assertIn(MEDILAND_MARKER, self.contract_text(template_center_id=2))

    def test_a_center_without_its_own_copy_prints_the_bundled_contract(self):
        self.assertNotIn(MEDILAND_MARKER, self.contract_text(template_center_id=1))

    def test_the_request_carries_the_center(self):
        request = GenerateRequestSchema(client_id=1, template_id=1, template_center_id=2)

        self.assertEqual(request.template_center_id, 2)
        self.assertIsNone(GenerateRequestSchema(client_id=1, template_id=1).template_center_id)


if __name__ == "__main__":
    unittest.main()
