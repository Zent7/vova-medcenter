from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.blank_form import (  # noqa: E402
    BLANK_STATUS_FREE,
    BLANK_STATUS_ISSUED,
    BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
    BlankBatch,
    BlankForm,
)
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.document_template import DocumentTemplate  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.services.document_generator import _blank_reference_number, generate_document  # noqa: E402


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
POOL_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "templates"
    / "Templates"
    / "CправкаБассейн_шаблон.docx"
)


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


class PoolCertificateNumberTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_blank_reference_number_preserves_leading_zeros(self):
        blank = BlankForm(
            batch_id=1,
            blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
            series="БАСС",
            number_value=12226,
            full_number="БАСС0012226",
        )

        self.assertEqual(_blank_reference_number(blank), "0012226")

    def test_selected_blank_number_replaces_stale_client_reference_and_is_reused(self):
        original_generated_dir = settings.generated_documents_dir
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings.generated_documents_dir = temporary_directory
            try:
                with self.Session() as db:
                    center = Center(code="pool", name="Медцентр")
                    client = Client(
                        patient_number=1,
                        last_name="Иванов",
                        first_name="Иван",
                        middle_name="Иванович",
                        birth_date=date(1990, 1, 1),
                        sex="M",
                        reference_number="12225",
                    )
                    db.add_all([center, client])
                    db.flush()

                    first_encounter = Encounter(
                        center_id=center.id,
                        client_id=client.id,
                        encounter_date=date(2026, 8, 14),
                        payment_type="cash",
                    )
                    second_encounter = Encounter(
                        center_id=center.id,
                        client_id=client.id,
                        encounter_date=date(2026, 8, 15),
                        payment_type="cash",
                    )
                    template = DocumentTemplate(
                        code="pool-certificate-number-test",
                        name="бассейн",
                        file_name=POOL_TEMPLATE_PATH.name,
                        file_path=str(POOL_TEMPLATE_PATH),
                        template_type="docx",
                        output_format="docx",
                        requires_numbered_blank=False,
                        is_active=True,
                    )
                    batch = BlankBatch(
                        center_id=center.id,
                        blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                        series="БАСС",
                        number_from=12226,
                        number_to=12227,
                        number_width=5,
                        quantity=2,
                    )
                    db.add_all([first_encounter, second_encounter, template, batch])
                    db.flush()

                    first_blank = BlankForm(
                        batch_id=batch.id,
                        center_id=center.id,
                        blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                        series="БАСС",
                        number_value=12226,
                        full_number="БАСС12226",
                        status=BLANK_STATUS_FREE,
                    )
                    second_blank = BlankForm(
                        batch_id=batch.id,
                        center_id=center.id,
                        blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                        series="БАСС",
                        number_value=12227,
                        full_number="БАСС12227",
                        status=BLANK_STATUS_FREE,
                    )
                    db.add_all([first_blank, second_blank])
                    db.flush()

                    first_result = generate_document(
                        db,
                        template_id=template.id,
                        template_code=None,
                        client_id=client.id,
                        encounter_id=first_encounter.id,
                        blank_form_id=first_blank.id,
                    )
                    first_text = docx_text(Path(first_result.output_file_path))
                    self.assertIn("С П Р А В К А № 12226", first_text)
                    self.assertNotIn("С П Р А В К А № 12225", first_text)
                    self.assertEqual(first_result.blank_number, "БАСС12226")

                    repeated_result = generate_document(
                        db,
                        template_id=template.id,
                        template_code=None,
                        client_id=client.id,
                        encounter_id=first_encounter.id,
                        blank_form_id=first_blank.id,
                    )
                    repeated_text = docx_text(Path(repeated_result.output_file_path))
                    self.assertIn("С П Р А В К А № 12226", repeated_text)
                    self.assertEqual(repeated_result.blank_number, "БАСС12226")

                    next_result = generate_document(
                        db,
                        template_id=template.id,
                        template_code=None,
                        client_id=client.id,
                        encounter_id=second_encounter.id,
                        blank_form_id=second_blank.id,
                    )
                    next_text = docx_text(Path(next_result.output_file_path))
                    self.assertIn("С П Р А В К А № 12227", next_text)
                    self.assertEqual(next_result.blank_number, "БАСС12227")

                    db.commit()
                    db.refresh(first_blank)
                    db.refresh(second_blank)
                    self.assertEqual(first_blank.status, BLANK_STATUS_ISSUED)
                    self.assertEqual(second_blank.status, BLANK_STATUS_ISSUED)
            finally:
                settings.generated_documents_dir = original_generated_dir


if __name__ == "__main__":
    unittest.main()
