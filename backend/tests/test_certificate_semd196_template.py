from pathlib import Path
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.document_generator import _generate_docx  # noqa: E402
from app.services.seed import DOCTOR_ROLES, SERVICE_DOCTOR_ROLE_IDS  # noqa: E402
from app.services.template_catalog import (  # noqa: E402
    load_template_catalog,
    template_is_listed_on_templates_page,
    template_visit_type_code,
)


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
TEMPLATES_PATH = Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates"
MALE_TEMPLATE_PATH = TEMPLATES_PATH / "СЭМД-196.муж_шаблон.docx"
FEMALE_TEMPLATE_PATH = TEMPLATES_PATH / "СЭМД-196.жен_шаблон.docx"
MALE_086_TEMPLATE_PATH = TEMPLATES_PATH / "086у.муж_шаблон_2.docx"
SEMD196_SERVICE_LEGACY_IDS = (43, 44)
# Строки врачей бланка (как у 086у) и председатель, который выдаёт справку.
SEMD196_BLANK_DOCTOR_ROLES = {
    "therapist",
    "surgeon",
    "neurologist",
    "ophthalmologist",
    "otolaryngologist",
    "gynecologist",
    "chairman",
}


def part_text(path: Path, part: str) -> str:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read(part))
    return "".join(node.text or "" for node in root.iter(f"{{{W_NS}}}t"))


def header_paragraph_count(path: Path) -> int:
    with zipfile.ZipFile(path) as archive:
        return len(re.findall(r"<w:p[ >]", archive.read("word/header1.xml").decode("utf-8")))


def generate(template_path: Path, context: dict[str, str]) -> str:
    with tempfile.TemporaryDirectory() as temporary_directory:
        output_path = Path(temporary_directory) / template_path.name
        _generate_docx(template_path, output_path, context)
        return part_text(output_path, "word/document.xml")


class Semd196TemplateTests(unittest.TestCase):
    def setUp(self):
        self.context = {
            "ReferenceNumber": "0000015",
            "ClientCalc": "Иванов Иван Иванович",
            "BirthDateCalc": "01.02.2008",
            "qdfMain.AddressCalc": "г. Санкт-Петербург, пр. Заневский, д. 1",
            "VisitDate": "21.09.2026",
            "CompanyName": "СПбГУ",
            "Certificate086TherapistDoctor": "Петров П.П.",
            "Certificate086SurgeonDoctor": "Кузнецов К.К.",
            "Certificate086NeurologistDoctor": "Смирнова С.С.",
            "Certificate086OphthalmologistDoctor": "Орлов О.О.",
            "Certificate086OtolaryngologistDoctor": "Ларин Л.Л.",
            "Certificate086GynecologistDoctor": "Гусева Г.Г.",
            "Certificate086IssuerDoctor": "Чижов Ч.Ч.",
        }

    def test_catalog_lists_both_blanks_on_the_templates_page(self):
        catalog = {item["file_name"]: item for item in load_template_catalog()}

        self.assertEqual(catalog[FEMALE_TEMPLATE_PATH.name]["name"], "СЭМД-196 (Ж)")
        self.assertEqual(catalog[MALE_TEMPLATE_PATH.name]["name"], "СЭМД-196 (М)")
        for path in (FEMALE_TEMPLATE_PATH, MALE_TEMPLATE_PATH):
            self.assertEqual(catalog[path.name]["template_type"], "docx")
            self.assertTrue(template_is_listed_on_templates_page(path.name))
            self.assertEqual(template_visit_type_code(f"{catalog[path.name]['name']} {path.name}"), "086")

    def test_semd196_services_send_the_client_to_every_doctor_on_the_blank(self):
        # Без осмотра строка врача печатается с фамилией, набранной в бланке.
        role_code_by_legacy_id = {legacy_id: code for legacy_id, code, _, _ in DOCTOR_ROLES}
        for service_id in SEMD196_SERVICE_LEGACY_IDS:
            roles = {role_code_by_legacy_id[role_id] for role_id in SERVICE_DOCTOR_ROLE_IDS[service_id]}
            self.assertEqual(roles, SEMD196_BLANK_DOCTOR_ROLES, service_id)

    def test_header_names_semd_instead_of_the_cancelled_086_form(self):
        for path in (MALE_TEMPLATE_PATH, FEMALE_TEMPLATE_PATH):
            header = part_text(path, "word/header1.xml")
            self.assertEqual(header.strip(), "СЭМД-196")
            self.assertNotIn("834н", part_text(path, "word/document.xml") + header)
            self.assertNotIn("086", part_text(path, "word/document.xml") + header)

    def test_header_keeps_the_086_height_so_the_clinic_box_stays_on_the_page(self):
        # Реквизиты медцентра стоят в рамке, привязанной к первому абзацу:
        # шапка ниже — и рамка уезжает за верхний край листа.
        self.assertEqual(header_paragraph_count(MALE_TEMPLATE_PATH), header_paragraph_count(MALE_086_TEMPLATE_PATH))
        self.assertEqual(header_paragraph_count(FEMALE_TEMPLATE_PATH), 3)

    def test_male_certificate_prints_current_doctors_and_male_wording(self):
        text = generate(MALE_TEMPLATE_PATH, self.context)

        self.assertIn("Медицинская справка №0000015", text)
        self.assertIn("врачебное профессионально-консультативное заключение", text)
        self.assertIn("Иванов Иван Иванович", text)
        for doctor in ("Петров П.П.", "Кузнецов К.К.", "Смирнова С.С.", "Орлов О.О.", "Ларин Л.Л.", "Чижов Ч.Ч."):
            self.assertIn(doctor, text)
        self.assertIn("Пр здоров", text)
        self.assertIn("Годен к поступлению", text)
        self.assertNotIn("здорова", text)
        self.assertNotIn("Годна", text)
        self.assertNotIn("Гинеколог", text)
        self.assertNotIn("[", text)

    def test_female_certificate_keeps_gynecologist_row(self):
        text = generate(FEMALE_TEMPLATE_PATH, self.context)

        self.assertIn("Гинеколог", text)
        self.assertIn("Гусева Г.Г.", text)
        self.assertNotIn("Губская И.А.", text)
        self.assertIn("Кузнецов К.К.", text)
        self.assertIn("Годна к поступлению", text)
        self.assertNotIn("[", text)


if __name__ == "__main__":
    unittest.main()
