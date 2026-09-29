from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET
import zipfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.client import Client  # noqa: E402
from app.models.doctor_exam import DoctorExam  # noqa: E402
from app.services.document_generator import (  # noqa: E402
    _certificate_095_context_overrides,
    _certificate_095_doctor_context_overrides,
    _generate_docx,
)


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "templates"
    / "Templates"
    / "095У_справка_шаблон.docx"
)


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    return "".join(node.text or "" for node in root.iter(f"{{{W_NS}}}t"))


class Certificate095ChairmanFieldsTests(unittest.TestCase):
    def setUp(self):
        self.exam = DoctorExam(
            doctor_role_id="chairman",
            fields_json={
                "educationInstitution": "Гимназия № 227",
                "illnessDiagnosis": "ОРВИ",
                "sickLeaveEndDate": "15.09.2026",
                "sickLeaveExtensionStartDate": "16.09.2026",
                "sickLeaveExtensionEndDate": "20.09.2026",
                "diagnosis": "патология органа зрения не выявлено",
            },
        )

    def test_chairman_card_fills_the_095_rows(self):
        overrides = _certificate_095_context_overrides([self.exam])

        self.assertEqual(overrides["Certificate095EducationInstitution"], "Гимназия № 227")
        self.assertEqual(overrides["Certificate095Diagnosis"], "ОРВИ")
        # Поле даты в карточке даёт год из четырёх цифр, а рядом «Дата выдачи» и «с …»
        # печатаются как дд.мм.гг: даты одной строки должны выглядеть одинаково.
        self.assertEqual(overrides["Certificate095SickLeaveEnd"], "15.09.26")
        self.assertEqual(overrides["Certificate095ExtensionStart"], "16.09.26")
        self.assertEqual(overrides["Certificate095ExtensionEnd"], "20.09.26")

    def test_dates_that_are_not_complete_dates_are_printed_as_typed(self):
        exam = DoctorExam(
            doctor_role_id="chairman",
            fields_json={
                "sickLeaveEndDate": "15.09.26",
                "sickLeaveExtensionStartDate": "16.09",
                "sickLeaveExtensionEndDate": "до выздоровления",
            },
        )

        overrides = _certificate_095_context_overrides([exam])

        self.assertEqual(overrides["Certificate095SickLeaveEnd"], "15.09.26")
        self.assertEqual(overrides["Certificate095ExtensionStart"], "16.09")
        self.assertEqual(overrides["Certificate095ExtensionEnd"], "до выздоровления")

    def test_general_diagnosis_field_does_not_leak_into_the_095(self):
        exam = DoctorExam(
            doctor_role_id="chairman",
            fields_json={"diagnosis": "патология органа зрения не выявлено"},
        )

        overrides = _certificate_095_context_overrides([exam])

        self.assertEqual(overrides["Certificate095Diagnosis"], "")

    def test_visit_without_a_chairman_leaves_the_rows_empty(self):
        overrides = _certificate_095_context_overrides([])

        self.assertEqual(
            set(overrides.values()),
            {""},
        )

    def test_generated_095_prints_the_entered_rows(self):
        context = {
            "ReferenceNumber": "0000042",
            "ClientCalc": "Иванов Иван Иванович",
            "qdfMain.BirthDate": "24.07.2010",
            "VisitDate": "10.09.2026",
            "VisitDate_DATEFULL": "10 сентября 2026 г.",
        }
        context.update(_certificate_095_context_overrides([self.exam]))
        context.update(_certificate_095_doctor_context_overrides(Client(), [self.exam]))

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / TEMPLATE_PATH.name

            _generate_docx(TEMPLATE_PATH, output_path, context)

            text = docx_text(output_path)

        self.assertIn("Гимназия № 227", text)
        self.assertIn("ОРВИ", text)
        self.assertIn("15.09.26", text)
        self.assertIn("16.09.26", text)
        self.assertIn("20.09.26", text)
        self.assertNotIn("[Certificate095", text)


def print_095(fields: dict | None) -> str:
    """Текст справки 095у, напечатанной по карточке председателя с такими полями."""
    exams = [] if fields is None else [DoctorExam(doctor_role_id="chairman", fields_json=fields)]
    context = {
        "ReferenceNumber": "0000042",
        "ClientCalc": "Иванов Иван Иванович",
        "qdfMain.BirthDate": "24.07.2010",
        "VisitDate": "10.09.26",
        "VisitDate_DATEFULL": "10.09.26",
    }
    context.update(_certificate_095_context_overrides(exams))
    context.update(_certificate_095_doctor_context_overrides(Client(), exams))

    with tempfile.TemporaryDirectory() as temporary_directory:
        output_path = Path(temporary_directory) / TEMPLATE_PATH.name
        _generate_docx(TEMPLATE_PATH, output_path, context)
        return docx_text(output_path)


class Certificate095ChoiceFieldsTests(unittest.TestCase):
    """«Школа / детсад», статус обучающегося и контакт с инфекционными больными."""

    def overrides(self, fields: dict) -> dict[str, str]:
        return _certificate_095_context_overrides([DoctorExam(doctor_role_id="chairman", fields_json=fields)])

    def test_card_without_the_choice_fields_prints_what_the_card_shows_by_default(self):
        overrides = self.overrides({})

        self.assertEqual(overrides["Certificate095InstitutionKind"], "школу")
        self.assertEqual(overrides["Certificate095StudentStatus"], "Учащемуся")
        self.assertEqual(overrides["Certificate095InfectiousContact"], "нет")
        self.assertEqual(overrides["Certificate095InfectiousContactWho"], "")

    def test_preschool_child_replaces_the_school_wording(self):
        overrides = self.overrides(
            {
                "certificate095KindSchool": False,
                "certificate095KindPreschool": True,
                "certificate095StatusPupil": False,
                "certificate095StatusChild": True,
            }
        )

        self.assertEqual(overrides["Certificate095InstitutionKind"], "детское дошкольное учреждение")
        self.assertEqual(
            overrides["Certificate095StudentStatus"], "Ребенку, посещающему дошкольное учреждение"
        )

    def test_several_marks_are_printed_in_the_order_of_the_blank(self):
        overrides = self.overrides(
            {
                "certificate095KindSchool": True,
                "certificate095KindPreschool": True,
                "certificate095StatusStudent": True,
                "certificate095StatusPupil": True,
                "certificate095StatusChild": False,
            }
        )

        self.assertEqual(overrides["Certificate095InstitutionKind"], "школу, детское дошкольное учреждение")
        self.assertEqual(overrides["Certificate095StudentStatus"], "Студенту, учащемуся")

    def test_nothing_marked_prints_nothing(self):
        overrides = self.overrides(
            {
                "certificate095KindSchool": False,
                "certificate095KindPreschool": False,
                "certificate095StatusStudent": False,
                "certificate095StatusPupil": False,
                "certificate095StatusChild": False,
            }
        )

        self.assertEqual(overrides["Certificate095InstitutionKind"], "")
        self.assertEqual(overrides["Certificate095StudentStatus"], "")

    def test_contact_with_infectious_patients_prints_who(self):
        overrides = self.overrides(
            {
                "certificate095InfectiousContact": "ДА",
                "certificate095InfectiousContactWho": "ветряная оспа,\nскарлатина",
            }
        )

        self.assertEqual(overrides["Certificate095InfectiousContact"], "да")
        self.assertEqual(overrides["Certificate095InfectiousContactWho"], "какими: ветряная оспа, скарлатина")

    def test_who_written_earlier_is_not_printed_after_switching_back_to_no(self):
        overrides = self.overrides(
            {"certificate095InfectiousContact": "НЕТ", "certificate095InfectiousContactWho": "ветряная оспа"}
        )

        self.assertEqual(overrides["Certificate095InfectiousContact"], "нет")
        self.assertEqual(overrides["Certificate095InfectiousContactWho"], "")

    def test_yes_without_who_leaves_the_line_for_handwriting(self):
        overrides = self.overrides({"certificate095InfectiousContact": "ДА"})

        self.assertEqual(overrides["Certificate095InfectiousContact"], "да")
        self.assertEqual(overrides["Certificate095InfectiousContactWho"], "")

    def test_printed_095_has_the_choices_and_none_of_the_underline_hints(self):
        text = print_095(
            {
                "certificate095KindSchool": False,
                "certificate095KindPreschool": True,
                "certificate095StatusPupil": False,
                "certificate095StatusChild": True,
                "certificate095InfectiousContact": "ДА",
                "certificate095InfectiousContactWho": "ветряная оспа",
                "educationInstitution": "Детский сад № 12",
            }
        )

        self.assertIn("посещающего детское дошкольное учреждение", text)
        self.assertIn("Ребенку, посещающему дошкольное учреждение", text)
        self.assertIn("Детский сад № 12", text)
        self.assertIn("Иванов Иван Иванович", text)
        self.assertIn("24.07.2010", text)
        self.assertIn("больными ____________да", text)
        self.assertIn("какими: ветряная оспа", text)
        self.assertNotIn("нужное подчеркнуть", text)
        self.assertNotIn("подчеркнуть, вписать", text)
        self.assertNotIn("(нет, да, какими)", text)
        self.assertNotIn("школу", text)
        self.assertNotIn("[Certificate095", text)

    def test_every_token_of_the_bundled_template_is_provided_by_the_print(self):
        with zipfile.ZipFile(TEMPLATE_PATH) as archive:
            document = archive.read("word/document.xml").decode("utf-8")
        tokens = set(re.findall(r"\[(Certificate095\w+)\]", re.sub(r"<[^>]+>", "", document)))
        provided = set(_certificate_095_context_overrides([])) | set(
            _certificate_095_doctor_context_overrides(Client(), [])
        )

        self.assertTrue(tokens)
        self.assertEqual(tokens - provided, set())

    def test_printed_values_are_not_red(self):
        """Метки шаблона были набраны красным, и значения выходили на бланке красными."""
        with zipfile.ZipFile(TEMPLATE_PATH) as archive:
            document = archive.read("word/document.xml").decode("utf-8")

        self.assertNotIn("FF0000", document)


if __name__ == "__main__":
    unittest.main()
