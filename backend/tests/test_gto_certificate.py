from datetime import date
from decimal import Decimal
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app.models  # noqa: F401,E402
from app.db.base import Base
from app.models.center import Center
from app.models.client import Client
from app.models.doctor_exam import DoctorExam
from app.models.document_template import DocumentTemplate
from app.models.encounter import Encounter
from app.models.encounter_service import EncounterService
from app.models.service import Service
from app.services import document_generator as generator
from app.services.seed import _ensure_service_catalog
from app.services.template_catalog import sync_document_template_catalog, template_is_listed_on_templates_page


def document_text(path):
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    return "".join(root.itertext())


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def document_paragraphs(path):
    """Абзацы документа: (текст, зачёркнут ли он целиком)."""
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    paragraphs = []
    for paragraph in root.iter(f"{W}p"):
        runs = [run for run in paragraph.iter(f"{W}r") if "".join(run.itertext()).strip()]
        text = "".join(paragraph.itertext()).strip()
        struck = bool(runs) and all(run.find(f"{W}rPr/{W}strike") is not None for run in runs)
        paragraphs.append((text, struck))
    return paragraphs


ADMISSION_LINES = (
    "к тренировочным мероприятиям",
    "к участию в спортивных соревнованиях",
    "к участию в физкультурных мероприятиях",
    "к выполнению комплекса ГТО",
)


class GtoCertificateTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.output = tempfile.TemporaryDirectory()
        self.old_service = Service(code="legacy-service-4", legacy_source_id=4, name="Справка ГТО 1144", price=1000)
        self.db.add(self.old_service)
        self.db.commit()
        self.old_id = self.old_service.id
        _ensure_service_catalog(self.db)
        sync_document_template_catalog(self.db)
        self.db.add_all([
            Center(id=1, code="test", name="Тест"),
            Client(id=1, patient_number=1, last_name="Иванов", first_name="Иван", middle_name="Иванович", birth_date=date(1990, 1, 28), reference_number="ГТО-123"),
            Encounter(id=1, client_id=1, center_id=1, encounter_date=date(2026, 9, 22), total_amount=1500, payment_type="cash"),
            EncounterService(encounter_id=1, service_id=self.old_id, quantity=1, unit_price=1500, line_total=1500),
            DoctorExam(client_id=1, encounter_id=1, doctor_role_id="therapist", doctor_name="Тестов Т.Т.", fields_json={}),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.output.cleanup()

    def generate(self, file_name):
        template = self.db.scalar(select(DocumentTemplate).where(DocumentTemplate.file_name == file_name))
        with patch.object(generator.settings, "generated_documents_dir", self.output.name):
            return generator.generate_document(self.db, template_id=template.id, template_code=None, client_id=1, encounter_id=1)

    def test_existing_service_is_updated_without_duplicate_and_contract_uses_exact_name(self):
        _ensure_service_catalog(self.db)
        services = self.db.scalars(select(Service).where(Service.legacy_source_id == 4)).all()
        self.assertEqual(len(services), 1)
        self.assertEqual(services[0].id, self.old_id)
        self.assertEqual(services[0].name, "справка ГТО")
        self.assertEqual(services[0].price, Decimal("1500.00"))
        result = self.generate("Договор_шаблон_2.docx")
        self.assertEqual(result.generated_fields["Services"], "справка ГТО")
        text = document_text(result.output_file_path)
        self.assertIn("справка ГТО", text)
        self.assertNotIn("1144", text)

    def test_new_certificate_is_listed_and_fills_patient_dates_and_therapist(self):
        self.assertTrue(template_is_listed_on_templates_page("ГТО_шаблон.docx"))
        result = self.generate("ГТО_шаблон.docx")
        text = document_text(result.output_file_path)
        for value in ("Иванов", "Иван", "Иванович", "28.01.90", "ГТО-123", "22.09.26", "22.09.2027", "Тестов Т.Т."):
            self.assertIn(value, text)
        self.assertNotRegex(text, r"\[[A-Za-z][^\]]*\]")
        self.assertIn("484н", text)

    def test_validity_uses_chairman_date_and_clamps_leap_day(self):
        self.db.add(DoctorExam(client_id=1, encounter_id=1, doctor_role_id="chairman", doctor_name="Другой Д.Д.", fields_json={"examDate": "29.02.2024"}))
        self.db.commit()
        result = self.generate("ГТО_шаблон.docx")
        text = document_text(result.output_file_path)
        self.assertIn("29.02.24", text)
        self.assertIn("28.02.2025", text)
        self.assertIn("Тестов Т.Т.", text)
        self.assertNotIn("Другой Д.Д.", text)

    def add_chairman(self, **fields):
        self.db.add(DoctorExam(client_id=1, encounter_id=1, doctor_role_id="chairman", doctor_name="Председателев П.П.", fields_json=fields))
        self.db.commit()

    def struck_admission_lines(self, result):
        paragraphs = document_paragraphs(result.output_file_path)
        lines = {}
        for line in ADMISSION_LINES:
            matches = [struck for text, struck in paragraphs if line in text]
            self.assertEqual(len(matches), 1, f"строка «{line}» должна быть в справке один раз")
            lines[line] = matches[0]
        return [line for line, struck in lines.items() if struck]

    def test_chairman_card_fills_athlete_block(self):
        self.add_chairman(
            gtoAthleteRegistryNumber="РН-77",
            gtoEventName="Фестиваль\nГТО",
            gtoSportKind="Плавание",
            gtoSportDiscipline="Вольный стиль",
            gtoTrainingStage="Этап начальной подготовки",
        )
        result = self.generate("ГТО_шаблон.docx")
        paragraphs = [text for text, _ in document_paragraphs(result.output_file_path)]
        for expected in (
            "Реестровый номер лица(спортсмена): РН-77",
            "Название мероприятия: Фестиваль ГТО",
            "Вид спорта: Плавание",
            "Спортивная дисциплина: Вольный стиль",
            "Этап спортивной подготовки: Этап начальной подготовки",
        ):
            self.assertIn(expected, paragraphs)
        self.assertEqual(result.generated_fields["GtoSportKind"], "Плавание")

    def test_without_chairman_card_everything_is_admitted_and_there_are_no_restrictions(self):
        result = self.generate("ГТО_шаблон.docx")
        self.assertEqual(self.struck_admission_lines(result), [])
        paragraphs = [text for text, _ in document_paragraphs(result.output_file_path)]
        self.assertIn("Ограничения, в том числе физических нагрузок, сроки ограничений: НЕТ", paragraphs)
        self.assertIn("Название мероприятия:", paragraphs)

    def test_unchecked_admission_lines_are_struck_out_but_stay_in_the_certificate(self):
        self.add_chairman(gtoAdmitCompetitions=False, gtoAdmitComplex=False, gtoAdmitTraining=True)
        result = self.generate("ГТО_шаблон.docx")
        self.assertEqual(
            self.struck_admission_lines(result),
            ["к участию в спортивных соревнованиях", "к выполнению комплекса ГТО"],
        )
        self.assertNotRegex(document_text(result.output_file_path), r"\[[A-Za-z][^\]]*\]")

    def test_restrictions_are_printed_only_when_the_card_says_yes(self):
        self.add_chairman(gtoRestrictions="ДА", gtoRestrictionsText="Без прыжков  и бега\nдо 01.12.2026")
        result = self.generate("ГТО_шаблон.docx")
        paragraphs = [text for text, _ in document_paragraphs(result.output_file_path)]
        self.assertIn("Ограничения, в том числе физических нагрузок, сроки ограничений: ДА", paragraphs)
        self.assertIn("Описать: Без прыжков и бега до 01.12.2026", paragraphs)

    def test_stale_restrictions_text_is_not_printed_after_switching_to_no(self):
        self.add_chairman(gtoRestrictions="НЕТ", gtoRestrictionsText="Без прыжков")
        result = self.generate("ГТО_шаблон.docx")
        text = document_text(result.output_file_path)
        self.assertIn("сроки ограничений: НЕТ", text)
        self.assertNotIn("Без прыжков", text)

    def test_marker_split_across_runs_is_found_and_removed(self):
        """Word режет метку на куски, когда заказчик правит рядом текст."""
        body = (
            "<w:p><w:r><w:t>- к выполнению комплекса ГТО</w:t></w:r><w:r><w:t>[Gto</w:t></w:r>"
            "<w:r><w:rPr><w:b/></w:rPr><w:t>AdmitComplex]</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>- к тренировочным мероприятиям;</w:t></w:r></w:p>"
        )
        with tempfile.TemporaryDirectory() as directory:
            template = Path(directory) / "template.docx"
            with zipfile.ZipFile(template, "w") as archive:
                archive.writestr("word/document.xml", f'<w:document xmlns:w="{W[1:-1]}"><w:body>{body}</w:body></w:document>')
            output = Path(directory) / "output.docx"
            generator._generate_docx(template, output, {"GtoAdmitComplex": "", "GtoAdmitComplexStruck": "1"})
            paragraphs = document_paragraphs(output)
        self.assertEqual(
            paragraphs,
            [("- к выполнению комплекса ГТО", True), ("- к тренировочным мероприятиям;", False)],
        )

    def test_card_field_keys_match_the_frontend_template(self):
        """Карточка сохраняет поля под теми же ключами, что читает печать."""
        template_js = Path(__file__).resolve().parents[2] / "frontend" / "public" / "demo" / "doctor-templates.js"
        frontend_keys = set(re.findall(r'key: "(gto[A-Za-z]+)"', template_js.read_text(encoding="utf-8-sig")))
        backend_keys = (
            {field for _token, field in generator.GTO_ATHLETE_FIELDS}
            | {field for _token, field in generator.GTO_ADMISSION_LINES}
            | {"gtoRestrictions", "gtoRestrictionsText"}
        )
        self.assertEqual(frontend_keys, backend_keys)

    def test_special_characters_in_card_text_do_not_break_the_document(self):
        self.add_chairman(gtoEventName='Кубок Р&К <финал> \\1 "А"', gtoRestrictions="ДА", gtoRestrictionsText="1 < 2 & 3")
        result = self.generate("ГТО_шаблон.docx")
        paragraphs = [text for text, _ in document_paragraphs(result.output_file_path)]
        self.assertIn('Название мероприятия: Кубок Р&К <финал> \\1 "А"', paragraphs)
        self.assertIn("Описать: 1 < 2 & 3", paragraphs)

    def test_missing_therapist_does_not_invent_a_signature(self):
        self.db.query(DoctorExam).delete()
        self.db.commit()
        result = self.generate("ГТО_шаблон.docx")
        self.assertEqual(result.generated_fields["GtoTherapistDoctor"], "")


if __name__ == "__main__":
    unittest.main()
