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
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.doctor_exam import DoctorExam  # noqa: E402
from app.models.document_template import DocumentTemplate  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.models.service import DoctorRole  # noqa: E402
from app.services.document_generator import generate_document  # noqa: E402


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
POOL_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "templates"
    / "Templates"
    / "CправкаБассейн_шаблон.docx"
)

DERMATOLOGIST_NAME = "Мехдиева Н.Ш.К."
THERAPIST_NAME = "Казаков И.В."
CHAIRMAN_NAME = "Председателев С.П."


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


class PoolCertificateDoctorsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _generate(self, roles: dict[str, str]) -> str:
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
                    )
                    db.add_all([center, client])
                    db.flush()

                    encounter = Encounter(
                        center_id=center.id,
                        client_id=client.id,
                        encounter_date=date(2026, 8, 25),
                        payment_type="cash",
                    )
                    template = DocumentTemplate(
                        code="pool-certificate-doctors-test",
                        name="бассейн",
                        file_name=POOL_TEMPLATE_PATH.name,
                        file_path=str(POOL_TEMPLATE_PATH),
                        template_type="docx",
                        output_format="docx",
                        requires_numbered_blank=False,
                        is_active=True,
                    )
                    db.add_all([encounter, template])
                    db.flush()

                    for index, (role_code, doctor_name) in enumerate(roles.items(), start=1):
                        db.add(
                            DoctorRole(
                                code=role_code,
                                name=role_code,
                                full_name=doctor_name,
                                sort_order=index * 10,
                            )
                        )
                        db.add(
                            DoctorExam(
                                client_id=client.id,
                                encounter_id=encounter.id,
                                doctor_role_id=role_code,
                                doctor_name=doctor_name,
                                is_completed=True,
                                fields_json={},
                            )
                        )
                    db.flush()

                    result = generate_document(
                        db,
                        template_id=template.id,
                        template_code=None,
                        client_id=client.id,
                        encounter_id=encounter.id,
                    )
                    return docx_text(Path(result.output_file_path))
            finally:
                settings.generated_documents_dir = original_generated_dir

    def test_each_line_takes_the_doctor_of_its_own_exam(self):
        text = self._generate(
            {
                "dermatologist": DERMATOLOGIST_NAME,
                "therapist": THERAPIST_NAME,
                "chairman": CHAIRMAN_NAME,
            }
        )

        self.assertNotIn("[Pool", text)
        dermatologist_line = text.index("Дерматолог:")
        therapist_line = text.index("Терапевт:")
        certificate_line = text.index("Справка действительна до")
        self.assertLess(dermatologist_line, therapist_line)
        self.assertLess(therapist_line, certificate_line)

        self.assertIn(DERMATOLOGIST_NAME, text[dermatologist_line:therapist_line])
        self.assertIn(THERAPIST_NAME, text[therapist_line:certificate_line])
        self.assertIn(CHAIRMAN_NAME, text[certificate_line:])

    def test_missing_exam_falls_back_to_the_signing_doctor(self):
        text = self._generate({"therapist": THERAPIST_NAME, "chairman": CHAIRMAN_NAME})

        self.assertNotIn("[Pool", text)
        dermatologist_line = text.index("Дерматолог:")
        therapist_line = text.index("Терапевт:")
        certificate_line = text.index("Справка действительна до")

        self.assertIn(CHAIRMAN_NAME, text[dermatologist_line:therapist_line])
        self.assertIn(THERAPIST_NAME, text[therapist_line:certificate_line])
        self.assertIn(CHAIRMAN_NAME, text[certificate_line:])


if __name__ == "__main__":
    unittest.main()
