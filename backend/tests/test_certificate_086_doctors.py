from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.client import Client  # noqa: E402
from app.models.doctor_exam import DoctorExam  # noqa: E402
from app.services.document_generator import (  # noqa: E402
    _certificate_086_doctor_context_overrides,
    _generate_docx,
)


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
TEMPLATES_PATH = Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates"
MALE_TEMPLATE_PATH = TEMPLATES_PATH / "086у.муж_шаблон_2.docx"
FEMALE_TEMPLATE_PATH = TEMPLATES_PATH / "086у.жен_шаблон.docx"
CONTRACT_TEMPLATE_PATH = TEMPLATES_PATH / "082у_шаблон.docx"


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    return "".join(node.text or "" for node in root.iter(f"{{{W_NS}}}t"))


def generate(template_path: Path, context: dict[str, str]) -> str:
    with tempfile.TemporaryDirectory() as temporary_directory:
        output_path = Path(temporary_directory) / template_path.name
        _generate_docx(template_path, output_path, context)
        return docx_text(output_path)


class Certificate086DoctorsTests(unittest.TestCase):
    def setUp(self):
        self.context = {
            "ReferenceNumber": "0000123",
            "ClientCalc": "Иванова Мария Петровна",
            "BirthDateCalc": "01.02.2005",
            "VisitDate": "23.08.2026",
            "Certificate086TherapistDoctor": "Петров П.П.",
            "Certificate086SurgeonDoctor": "Кузнецов К.К.",
            "Certificate086NeurologistDoctor": "Смирнова С.С.",
            "Certificate086OphthalmologistDoctor": "Орлов О.О.",
            "Certificate086OtolaryngologistDoctor": "Ларин Л.Л.",
            "Certificate086GynecologistDoctor": "Гусева Г.Г.",
            "Certificate086IssuerDoctor": "Чижов Ч.Ч.",
        }

    def test_context_overrides_take_doctors_from_exams(self):
        client = Client(last_name="Иванова", first_name="Мария", middle_name="Петровна")
        exams = [
            DoctorExam(doctor_role_id="therapist", doctor_name="Петров П.П."),
            DoctorExam(doctor_role_id="surgeon", doctor_name="Кузнецов К.К."),
            DoctorExam(doctor_role_id="chairman", doctor_name="Чижов Ч.Ч."),
        ]

        overrides = _certificate_086_doctor_context_overrides(client, exams)

        self.assertEqual(overrides["Certificate086TherapistDoctor"], "Петров П.П.")
        self.assertEqual(overrides["Certificate086SurgeonDoctor"], "Кузнецов К.К.")
        self.assertEqual(overrides["Certificate086IssuerDoctor"], "Чижов Ч.Ч.")
        self.assertEqual(overrides["Certificate086NeurologistDoctor"], "")

    def test_issuer_falls_back_to_therapist(self):
        client = Client(last_name="Иванова", first_name="Мария", middle_name="Петровна")
        exams = [DoctorExam(doctor_role_id="therapist", doctor_name="Петров П.П.")]

        overrides = _certificate_086_doctor_context_overrides(client, exams)

        self.assertEqual(overrides["Certificate086IssuerDoctor"], "Петров П.П.")

    def test_male_certificate_uses_current_doctors(self):
        text = generate(MALE_TEMPLATE_PATH, self.context)

        self.assertIn("Врач-терапевт", text)
        for doctor in ("Петров П.П.", "Кузнецов К.К.", "Смирнова С.С.", "Орлов О.О.", "Ларин Л.Л.", "Чижов Ч.Ч."):
            self.assertIn(doctor, text)
        for template_doctor in ("Напасов", "Плотников А.А.", "Пирожков В.И.", "Изория"):
            self.assertNotIn(template_doctor, text)
        # Главный врач организации остаётся из шаблона.
        self.assertIn("Ф.И.О Главного врача медицинской организации", text)
        self.assertEqual(text.count("Сибирцев В.А"), 1)

    def test_female_certificate_gets_surgeon_name_added(self):
        text = generate(FEMALE_TEMPLATE_PATH, self.context)

        self.assertIn("хирургической патологии не выявлено", text)
        self.assertIn("Кузнецов К.К.", text)
        self.assertIn("Гусева Г.Г.", text)
        self.assertNotIn("Губская И.А.", text)

    def test_rows_without_exam_keep_template_doctor(self):
        text = generate(
            MALE_TEMPLATE_PATH,
            {**self.context, "Certificate086SurgeonDoctor": "", "Certificate086OphthalmologistDoctor": ""},
        )

        self.assertIn("Напасов", text)
        self.assertIn("Пирожков В.И.", text)
        self.assertIn("Петров П.П.", text)
        self.assertNotIn("Кузнецов К.К.", text)

    def test_other_templates_are_not_touched(self):
        text = generate(
            CONTRACT_TEMPLATE_PATH,
            {key: value for key, value in self.context.items() if key.startswith("Certificate086")},
        )

        self.assertIn("Сибирцев В.А", text)
        self.assertNotIn("Петров П.П.", text)


if __name__ == "__main__":
    unittest.main()
