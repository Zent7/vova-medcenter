"""Справка 095/у печатает врача-терапевта под подписью врача.

У услуги 095 один врач — терапевт. ФИО берётся так же, как в других справках:
из справочника врачей медцентра, а без него — из карточки клиента.
"""

from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


os.environ.setdefault("ALLOW_SQLITE", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.center_doctor_name import CenterDoctorName  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.doctor_exam import DoctorExam  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.models.service import DoctorRole  # noqa: E402
from app.services.document_generator import (  # noqa: E402
    _certificate_095_doctor_context_overrides,
    _generate_docx,
    _load_encounter_document_values,
)


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "templates"
    / "Templates"
    / "095У_справка_шаблон.docx"
)
THERAPIST = "Сибирцев Вячеслав Александрович"


def docx_paragraphs(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    return [
        "".join(node.text or "" for node in paragraph.iter(f"{{{W_NS}}}t")).strip()
        for paragraph in root.iter(f"{{{W_NS}}}p")
    ]


class Certificate095TherapistTests(unittest.TestCase):
    def test_therapist_of_the_visit_signs_the_095(self):
        client = Client(last_name="Иванов", first_name="Иван")
        exams = [
            DoctorExam(doctor_role_id="chairman", doctor_name="Председатель Комиссии"),
            DoctorExam(doctor_role_id="therapist", doctor_name=THERAPIST),
        ]

        overrides = _certificate_095_doctor_context_overrides(client, exams)

        self.assertEqual(overrides["Certificate095TherapistDoctor"], THERAPIST)

    def test_exam_without_a_name_falls_back_to_the_client_card(self):
        """Без ФИО в справочнике центра в осмотре остаётся название специальности."""
        client = Client(last_name="Иванов", first_name="Иван", doctor_therapist="Петров П.П.")
        exams = [DoctorExam(doctor_role_id="therapist", doctor_name="Терапевт")]

        overrides = _certificate_095_doctor_context_overrides(client, exams)

        self.assertEqual(overrides["Certificate095TherapistDoctor"], "Петров П.П.")

    def test_chairman_does_not_stand_in_for_the_therapist(self):
        client = Client(last_name="Иванов", first_name="Иван")
        exams = [DoctorExam(doctor_role_id="chairman", doctor_name="Председатель Комиссии")]

        overrides = _certificate_095_doctor_context_overrides(client, exams)

        self.assertEqual(overrides["Certificate095TherapistDoctor"], "")

    def test_print_takes_the_therapist_from_the_center_directory(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            client = Client(
                patient_number=1,
                last_name="Иванов",
                first_name="Иван",
                birth_date=date(2010, 7, 24),
                created_by_user_id=1,
            )
            center = Center(code="test", name="Тестовый центр", address="")
            db.add_all([client, center])
            db.flush()
            encounter = Encounter(
                center_id=center.id,
                client_id=client.id,
                encounter_date=date(2026, 9, 10),
                payment_type="cash",
                created_by_user_id=1,
            )
            db.add(encounter)
            db.flush()
            db.add(DoctorRole(id=1, code="therapist", name="Терапевт"))
            db.add(CenterDoctorName(center_id=center.id, doctor_role_code="therapist", full_name=THERAPIST))
            # Так осмотр терапевта заводит автозаполнение услуги 095.
            db.add(
                DoctorExam(
                    client_id=client.id,
                    encounter_id=encounter.id,
                    doctor_role_id="therapist",
                    doctor_name="Терапевт",
                    fields_json={},
                    is_completed=True,
                    created_by_user_id=1,
                )
            )
            db.commit()

            runtime_values = _load_encounter_document_values(db, client, encounter)

        self.assertEqual(runtime_values["context_overrides"]["Certificate095TherapistDoctor"], THERAPIST)

    def test_generated_095_prints_the_therapist_under_the_doctor_signature(self):
        context = {
            "ReferenceNumber": "0000042",
            "ClientCalc": "Иванов Иван Иванович",
            "VisitDate": "10.09.2026",
            "VisitDate_DATEFULL": "10 сентября 2026 г.",
            "Certificate095TherapistDoctor": THERAPIST,
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / TEMPLATE_PATH.name
            _generate_docx(TEMPLATE_PATH, output_path, context)
            paragraphs = [text for text in docx_paragraphs(output_path) if text]

        signature_index = next(index for index, text in enumerate(paragraphs) if "Подпись врача" in text)
        # Строка врача — последняя на бланке, сразу под подписью.
        self.assertEqual(paragraphs[signature_index + 1:], [f"Врач-терапевт {THERAPIST}"])
        self.assertNotIn("[Certificate095TherapistDoctor]", "".join(paragraphs))


if __name__ == "__main__":
    unittest.main()
