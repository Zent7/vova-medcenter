from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


os.environ.setdefault("ALLOW_SQLITE", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.document_template import DocumentTemplate  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.models.encounter_service import EncounterService  # noqa: E402
from app.models.service import Service  # noqa: E402
from app.services import document_generator  # noqa: E402


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_TEMPLATE_PATH = next(
    path
    for path in (REPOSITORY_ROOT / "assets" / "templates").rglob("*.docx")
    if path.stem.lower() == "договор_шаблон_2"
)


class ContractServiceGroupTests(unittest.TestCase):
    """Один договор на все услуги клиента за день, хотя строк журнала несколько."""

    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.output_dir = tempfile.TemporaryDirectory()

        self.center = Center(id=1, code="center-1", name="Медцентр 1")
        self.other_center = Center(id=2, code="center-2", name="Медцентр 2")
        self.client = Client(
            id=1,
            patient_number=1,
            last_name="Тестов",
            first_name="Тест",
            birth_date=date(1990, 1, 1),
        )
        self.services = {
            name: Service(id=index, code=f"service-{index}", name=name, price=Decimal("1000.00"), is_active=True)
            for index, name in enumerate(
                ["Медицинская комиссия", "ГС", "Профосмотр", "Справка в бассейн", "ЭКГ"],
                start=1,
            )
        }
        self.template = DocumentTemplate(
            id=1,
            code="contract",
            name="Договор на оказание платных медицинских услуг",
            file_name=CONTRACT_TEMPLATE_PATH.name,
            file_path=str(CONTRACT_TEMPLATE_PATH),
            template_type="docx",
        )
        self.db.add_all([self.center, self.other_center, self.client, *self.services.values(), self.template])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.output_dir.cleanup()

    def _encounter(self, service_name: str, *, encounter_date=date(2026, 9, 17), center_id=1, deleted=False):
        encounter = Encounter(
            center_id=center_id,
            client_id=self.client.id,
            encounter_date=encounter_date,
            payment_type="cash",
            total_amount=Decimal("1000.00"),
            deleted_at=datetime.now(timezone.utc) if deleted else None,
        )
        self.db.add(encounter)
        self.db.flush()
        self.db.add(
            EncounterService(
                encounter_id=encounter.id,
                service_id=self.services[service_name].id,
                quantity=1,
                unit_price=Decimal("1000.00"),
                line_total=Decimal("1000.00"),
            )
        )
        self.db.flush()
        return encounter

    def _generate(self, encounter: Encounter, template: DocumentTemplate | None = None):
        with patch.object(document_generator.settings, "generated_documents_dir", self.output_dir.name):
            return document_generator.generate_document(
                self.db,
                template_id=(template or self.template).id,
                template_code=None,
                client_id=self.client.id,
                encounter_id=encounter.id,
            )

    @staticmethod
    def _document_text(result) -> str:
        with zipfile.ZipFile(result.output_file_path) as archive:
            xml_text = archive.read("word/document.xml").decode("utf-8")
        return re.sub(r"<[^>]+>", "", xml_text)

    def test_contract_lists_every_service_of_the_day_from_any_journal_row(self):
        first = self._encounter("Медицинская комиссия")
        self._encounter("ГС")
        third = self._encounter("Профосмотр")
        self._encounter("Справка в бассейн", encounter_date=date(2026, 9, 16))
        self._encounter("ЭКГ", center_id=self.other_center.id)
        self._encounter("ЭКГ", deleted=True)
        self.db.commit()

        for encounter in (first, third):
            result = self._generate(encounter)
            text = self._document_text(result)
            self.assertEqual(result.generated_fields["ContractNumber"], f"Д-{first.id}")
            self.assertEqual(result.generated_fields["Services"], "Медицинская комиссия, ГС, Профосмотр")
            # Строка таблицы: №, услуга, количество, дата — каждая услуга отдельной строкой.
            self.assertIn("1Медицинская комиссия117.09.26", text)
            self.assertIn("2ГС117.09.26", text)
            self.assertIn("3Профосмотр117.09.26", text)
            self.assertNotIn("Справка в бассейн", text)
            self.assertNotIn("ЭКГ", text)

    def test_single_service_contract_keeps_its_own_number(self):
        encounter = self._encounter("Профосмотр")
        self.db.commit()

        result = self._generate(encounter)

        self.assertEqual(result.generated_fields["ContractNumber"], f"Д-{encounter.id}")
        self.assertIn("Профосмотр", self._document_text(result))

    def test_other_documents_keep_only_their_own_encounter_services(self):
        encounter = self._encounter("Медицинская комиссия")
        self._encounter("ГС")
        self.db.commit()

        values = document_generator._load_encounter_document_values(self.db, self.client, encounter)

        self.assertEqual(values["service_names"], ["Медицинская комиссия"])


if __name__ == "__main__":
    unittest.main()
