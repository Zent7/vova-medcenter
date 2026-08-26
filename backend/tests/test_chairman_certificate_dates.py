from pathlib import Path
from datetime import date
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET
import zipfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.doctor_exam import DoctorExam  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.services.document_context import build_document_context  # noqa: E402
from app.services.document_generator import (  # noqa: E402
    _chairman_certificate_date_context_overrides,
    _document_doctor_name_for_context,
    _generate_docx,
    _pool_doctor_context_overrides,
)


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates"
DATED_CERTIFICATE_TEMPLATES = (
    "CправкаБассейн_шаблон.docx",
    "ГТО1144_шаблон.docx",
)
DATED_XLS_CERTIFICATE_TEMPLATES = (
    "ГС НОВЫЙ ФОРМАТ.xls",
    "ГТ.xls",
    "СКК 070 новый формат.xls",
    "СКК 72 новый формат.xls",
    "СПОРТ.xls",
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


def document_root_tag(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml_text = archive.read("word/document.xml").decode("utf-8")
    start = xml_text.find("<w:document")
    end = xml_text.find(">", start)
    return xml_text[start:end]


class ChairmanCertificateDateTests(unittest.TestCase):
    def setUp(self):
        self.exam = DoctorExam(
            doctor_role_id="chairman",
            fields_json={"examDate": "05.07.2026"},
        )

    def test_chairman_exam_date_overrides_all_visit_date_variants(self):
        template = SimpleNamespace(file_name="CправкаБассейн_шаблон.docx", file_path=None)

        overrides = _chairman_certificate_date_context_overrides(template, [self.exam])

        self.assertEqual(overrides["VisitDate"], "05.07.26")
        self.assertEqual(overrides["VisitDate_DATEFULL"], "05.07.26")
        self.assertEqual(overrides["VisitDate_DAY"], "05")
        self.assertEqual(overrides["VisitDate_DATEMONTH"], "июля")
        self.assertEqual(overrides["VisitDate_YEAR"], "2026")
        self.assertEqual(overrides["PoolValidUntil"], "05.01.2027")

    def test_pool_validity_clamps_to_last_day_of_month(self):
        self.exam.fields_json = {"examDate": "31.08.2026"}
        template = SimpleNamespace(file_name="CправкаБассейн_шаблон.docx", file_path=None)

        overrides = _chairman_certificate_date_context_overrides(template, [self.exam])

        self.assertEqual(overrides["PoolValidUntil"], "28.02.2027")

    def test_unrelated_template_keeps_encounter_date_context(self):
        template = SimpleNamespace(file_name="Договор_шаблон.docx", file_path=None)

        self.assertEqual(_chairman_certificate_date_context_overrides(template, [self.exam]), {})

    def test_mail_xls_templates_use_chairman_exam_date(self):
        for template_name in DATED_XLS_CERTIFICATE_TEMPLATES:
            with self.subTest(template=template_name):
                template = SimpleNamespace(file_name=template_name, file_path=None)

                overrides = _chairman_certificate_date_context_overrides(template, [self.exam])

                self.assertEqual(overrides["VisitDate"], "05.07.26")
                self.assertEqual(overrides["VisitDate_DATEMONTH"], "июля")
                self.assertEqual(overrides["VisitDate_YEAR"], "2026")

    def test_070_birth_date_digit_tokens_follow_client_birth_date(self):
        client = Client(
            id=1,
            last_name="Иванов",
            first_name="Иван",
            birth_date=date(1999, 1, 28),
        )

        context = build_document_context(client)

        self.assertEqual(
            "".join(context[f"BirthDateCalc_DIGIT{index}"] for index in range(1, 9)),
            "28011999",
        )

    def test_pool_wording_follows_client_sex(self):
        male = Client(
            id=1,
            last_name="Иванов",
            first_name="Иван",
            birth_date=date(1999, 1, 28),
            sex="M",
        )
        female = Client(
            id=2,
            last_name="Иванова",
            first_name="Ирина",
            birth_date=date(1999, 1, 28),
            sex="F",
        )

        male_context = build_document_context(male)
        female_context = build_document_context(female)

        self.assertEqual(
            (male_context["PoolAdmission"], male_context["PoolHealthy"]),
            ("Допущен", "здоров"),
        )
        self.assertEqual(
            (female_context["PoolAdmission"], female_context["PoolHealthy"]),
            ("Допущена", "здорова"),
        )

    def test_pool_validity_falls_back_to_encounter_date(self):
        client = Client(
            id=1,
            last_name="Иванов",
            first_name="Иван",
            birth_date=date(1999, 1, 28),
            sex="M",
        )
        encounter = Encounter(
            id=10,
            client_id=1,
            center_id=1,
            encounter_date=date(2026, 8, 31),
        )

        context = build_document_context(client, encounter)

        self.assertEqual(context["PoolValidUntil"], "28.02.2027")

    def test_document_doctor_tracks_changed_chairman_name(self):
        self.exam.doctor_name = "Иванов И.И."
        self.assertEqual(_document_doctor_name_for_context([self.exam]), "Иванов И.И.")

        self.exam.doctor_name = "Петров П.П."
        self.assertEqual(_document_doctor_name_for_context([self.exam]), "Петров П.П.")

    def test_selected_certificate_templates_render_chairman_date(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            for template_name in DATED_CERTIFICATE_TEMPLATES:
                with self.subTest(template=template_name):
                    template = SimpleNamespace(file_name=template_name, file_path=None)
                    context = {
                        "ReferenceNumber": "12005",
                        "ClientCalc": "Иванов Иван Иванович",
                        "qdfMain.BirthDate": "28.01.99",
                        "BirthDateCalc": "28.01.99",
                        "BirthDateCalc_DIGIT1": "2",
                        "BirthDateCalc_DIGIT2": "8",
                        "BirthDateCalc_DIGIT3": "0",
                        "BirthDateCalc_DIGIT4": "1",
                        "BirthDateCalc_DIGIT5": "1",
                        "BirthDateCalc_DIGIT6": "9",
                        "BirthDateCalc_DIGIT7": "9",
                        "BirthDateCalc_DIGIT8": "9",
                        "SexCalc": "муж",
                        "PoolAdmission": "Допущен",
                        "PoolHealthy": "здоров",
                        "Doctor": "Петров П.П.",
                        **_chairman_certificate_date_context_overrides(template, [self.exam]),
                    }
                    context.update(
                        _pool_doctor_context_overrides(template, [self.exam], context)
                    )
                    output_path = output_dir / template_name

                    _generate_docx(TEMPLATES_DIR / template_name, output_path, context)

                    text = docx_text(output_path)
                    root_tag = document_root_tag(output_path)
                    source_root_tag = document_root_tag(TEMPLATES_DIR / template_name)
                    self.assertNotRegex(text, re.compile(r"\[VisitDate(?:_|\])"))
                    declared_prefixes = set(re.findall(r"xmlns:([A-Za-z_][\w.-]*)=", root_tag))
                    source_declared_prefixes = set(
                        re.findall(r"xmlns:([A-Za-z_][\w.-]*)=", source_root_tag)
                    )
                    source_ignorable_match = re.search(r'mc:Ignorable="([^"]+)"', source_root_tag)
                    if source_ignorable_match:
                        self.assertTrue(
                            set(source_ignorable_match.group(1).split()).issubset(
                                source_declared_prefixes
                            )
                        )
                    self.assertTrue(source_declared_prefixes.issubset(declared_prefixes))
                    if template_name.startswith("070"):
                        compact_text = re.sub(r"\s+", "", text)
                        self.assertIn("“05”июля2026года", compact_text)
                        self.assertIn("3.Датарождения28.01.1999", compact_text)
                        self.assertNotIn("14Января2026", compact_text)
                    else:
                        self.assertIn("05.07.26", text)
                        self.assertIn("28.01.99", text)

                    if "Бассейн" in template_name:
                        self.assertIn("06.02.96 № 65", text)
                        self.assertIn("Допущен по состоянию здоровья", text)
                        self.assertIn("Практически здоров", text)
                        self.assertIn("практически здоров", text)
                        self.assertIn("Справка действительна до 05.01.2027", text)
                        self.assertEqual(text.count("Петров П.П."), 3)
                        self.assertNotIn("[Pool", text)


if __name__ == "__main__":
    unittest.main()
