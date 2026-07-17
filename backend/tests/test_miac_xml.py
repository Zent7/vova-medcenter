from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.document_generator import (  # noqa: E402
    MIAC_NS,
    SOAP_NS,
    _build_miac_driver_xml,
    _build_miac_gims_xml,
    _build_miac_guard_xml,
    _resolve_miac_issued_blank,
    generate_document,
)
import app.models  # noqa: E402,F401
from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.blank_form import (  # noqa: E402
    BLANK_STATUS_FREE,
    BLANK_STATUS_ISSUED,
    BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
    BLANK_TYPE_GUARD_MEDICAL_CERTIFICATE,
    BlankBatch,
    BlankForm,
)
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.doctor_exam import DoctorExam  # noqa: E402
from app.models.document_template import DocumentTemplate  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.services.template_catalog import template_is_active_by_default  # noqa: E402
from app.services.blank_forms import resolve_required_blank_type  # noqa: E402


def make_client(*, address_text="г. Тверь", registration_text=""):
    return SimpleNamespace(
        last_name="Иванов & Партнёры",
        first_name="Иван <Иван>",
        middle_name="Иванович",
        birth_date=date(1980, 2, 1),
        address_text=address_text,
        registration_text=registration_text,
        snils="123-456-789 01",
    )


def make_exam(role, *, fields=None, completed=True, doctor="Врач & Партнёр"):
    return SimpleNamespace(
        doctor_role_id=role,
        fields_json=fields or {},
        is_completed=completed,
        doctor_name=doctor,
        diagnosis="",
        result_text="",
        comment="",
        completed_at=datetime(2026, 7, 13, 10, 30, tzinfo=timezone.utc) if completed else None,
        deleted_at=None,
    )


def make_blank():
    return SimpleNamespace(full_number="78 АА 1234567")


class MiacXmlTests(unittest.TestCase):
    def test_driver_xml_has_miac_structure_independent_flags_and_escaping(self):
        chairman = make_exam(
            "chairman",
            fields={
                "conclusion": "Не годен & требуется контроль",
                "categoryA": True,
                "categoryB": False,
                "categoryA1": False,
                "categoryB1": True,
                "categoryTractor": True,
                "categoryBoat": True,
                "restrictionAM": False,
                "restrictionBBE": True,
                "restrictionCCE": False,
                "indicationManual": True,
                "indicationAutomatic": False,
                "ekgConclusion": "ЭКГ <норма>",
                "laboratoryTest": "Анализы & норма",
            },
        )
        therapist = make_exam("therapist", fields={"conclusion": "Здоров & годен"})
        tree = _build_miac_driver_xml(
            make_client(address_text="Санкт-Петербург, Центральный район, Невский проспект, д. 1, кв. 2"),
            make_blank(),
            [chairman, therapist],
        )
        xml_bytes = ET.tostring(tree.getroot(), encoding="utf-8", xml_declaration=True)
        root = ET.fromstring(xml_bytes)
        ns = {"soapenv": SOAP_NS, "mb": MIAC_NS}

        self.assertEqual(root.tag, f"{{{SOAP_NS}}}Envelope")
        request = root.find("soapenv:Body/mb:fillGibddBlankV4Request", ns)
        self.assertIsNotNone(request)
        self.assertEqual(request.findtext("mb:blankInfo/mb:id", namespaces=ns), "78 АА 1234567")
        self.assertEqual(request.findtext("mb:clientInfo/mb:birthday", namespaces=ns), "1980-02-01")
        self.assertEqual(request.findtext("mb:clientInfo/mb:address/mb:type", namespaces=ns), "1")
        self.assertEqual(request.findtext("mb:clientInfo/mb:address/mb:place", namespaces=ns), "Санкт-Петербург")
        self.assertEqual(request.findtext("mb:clientInfo/mb:address/mb:city", namespaces=ns), "Санкт-Петербург")
        self.assertEqual(request.findtext("mb:conclusion/mb:medConclusion/mb:dateConclusion", namespaces=ns), "2026-07-13")
        self.assertEqual(request.findtext("mb:conclusion/mb:medConclusion/mb:contraindication", namespaces=ns), "true")
        self.assertEqual(request.findtext("mb:conclusion/mb:medConclusion/mb:indication", namespaces=ns), "true")
        self.assertEqual(request.findtext("mb:conclusion/mb:medConclusion/mb:restriction", namespaces=ns), "true")
        self.assertEqual(request.findtext("mb:category/mb:category/mb:categoryA", namespaces=ns), "true")
        self.assertEqual(request.findtext("mb:category/mb:subCategory/mb:subCategoryA1", namespaces=ns), "false")
        self.assertEqual(request.findtext("mb:category/mb:subCategory/mb:subCategoryB1", namespaces=ns), "true")
        self.assertEqual(request.findtext("mb:restrictions/mb:catAM", namespaces=ns), "false")
        self.assertEqual(request.findtext("mb:restrictions/mb:catBBE", namespaces=ns), "true")
        self.assertIn(b"&amp;", xml_bytes)
        self.assertIn(b"&lt;", xml_bytes)

    def test_driver_uses_registration_address_as_type_zero(self):
        chairman = make_exam("chairman", fields={"conclusion": "Годен"})
        tree = _build_miac_driver_xml(
            make_client(address_text="", registration_text="Московская область, г. Химки, ул. Мира, д. 5"),
            make_blank(),
            [chairman],
        )
        ns = {"soapenv": SOAP_NS, "mb": MIAC_NS}
        request = tree.getroot().find("soapenv:Body/mb:fillGibddBlankV4Request", ns)
        self.assertEqual(request.findtext("mb:clientInfo/mb:address/mb:type", namespaces=ns), "0")
        self.assertEqual(request.findtext("mb:clientInfo/mb:address/mb:city", namespaces=ns), "Химки")

    def test_guard_xml_uses_plain_root_and_russian_dates(self):
        chairman = make_exam("chairman", fields={"conclusion": "Годен & здоров"})
        tree = _build_miac_guard_xml(make_client(), make_blank(), [chairman])
        root = tree.getroot()
        self.assertEqual(root.tag, "BlankSecurity")
        self.assertEqual(root.findtext("Request/blankInfo/id"), "78 АА 1234567")
        self.assertEqual(root.findtext("SecurityBlank/userInfo/birthday"), "01.02.1980")
        self.assertEqual(root.findtext("SecurityBlank/medConclusion/dateConclusion"), "13.07.2026")
        self.assertEqual(root.findtext("SecurityBlank/medConclusion/conclusion"), "Годен & здоров")

    def test_gims_xml_matches_upload_structure_and_uses_patient_data(self):
        chairman = make_exam(
            "chairman",
            fields={
                "conclusion": "Не годен к управлению",
                "restrictionOnManagement": True,
                "reexaminationAfterBan": True,
            },
        )
        tree = _build_miac_gims_xml(
            make_client(address_text="Санкт-Петербург, Центральный район, Невский проспект, д. 1, кв. 2"),
            make_blank(),
            [chairman],
        )
        root = tree.getroot()
        ns = {"mb": MIAC_NS}

        self.assertEqual(root.tag, f"{{{MIAC_NS}}}fillShipBlankRequset")
        self.assertEqual(root.findtext("mb:blankInfo/mb:id", namespaces=ns), "78 АА 1234567")
        self.assertEqual(root.findtext("mb:blankInfo/mb:duplicate/mb:isDuplicated", namespaces=ns), "false")
        self.assertEqual(root.findtext("mb:clientInfo/mb:surname", namespaces=ns), "Иванов & Партнёры")
        self.assertEqual(root.findtext("mb:clientInfo/mb:birthday", namespaces=ns), "01.02.1980")
        self.assertEqual(root.findtext("mb:clientInfo/mb:snils", namespaces=ns), "12345678901")
        self.assertEqual(root.findtext("mb:clientInfo/mb:address/mb:type", namespaces=ns), "1")
        self.assertEqual(root.findtext("mb:clientInfo/mb:address/mb:town", namespaces=ns), "Санкт-Петербург")
        medical = root.find("mb:conclusion/mb:medConclusion", ns)
        self.assertEqual(medical.findtext("mb:contraindicationToManagement", namespaces=ns), "true")
        self.assertEqual(medical.findtext("mb:restrictionOnManagement", namespaces=ns), "true")
        self.assertEqual(medical.findtext("mb:reexaminationAfterBan", namespaces=ns), "true")
        self.assertEqual(medical.findtext("mb:dateConclusion", namespaces=ns), "13.07.2026")
        self.assertEqual(medical.findtext("mb:fioDoctor", namespaces=ns), "Врач & Партнёр")

    def test_gims_xml_requires_snils(self):
        client = make_client()
        client.snils = ""
        with self.assertRaisesRegex(ValueError, "корректный СНИЛС пациента"):
            _build_miac_gims_xml(client, make_blank(), [make_exam("chairman", fields={"conclusion": "Годен"})])

    def test_missing_completed_chairman_is_rejected_with_field_list(self):
        with self.assertRaisesRegex(ValueError, "завершённый осмотр председателя комиссии"):
            _build_miac_guard_xml(make_client(), make_blank(), [])

    def test_only_canonical_miac_xml_templates_are_active(self):
        self.assertTrue(template_is_active_by_default("Водительская(новая).xml"))
        self.assertTrue(template_is_active_by_default("Чод_новый.xml"))
        self.assertTrue(template_is_active_by_default("ГИМС_шаблон_для_загрузки_из_файла.xml"))
        self.assertFalse(template_is_active_by_default("Водительская_шаблон.xml"))
        self.assertFalse(template_is_active_by_default("Чод.xml"))
        self.assertTrue(template_is_active_by_default("Охрана_шаблон.docx"))


class MiacBlankReuseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_guard_print_variant_requires_guard_blank_for_shared_xls_template(self):
        template = SimpleNamespace(
            name="ВСЕ НУЖНЫЕ ШАБЛОНЫ",
            requires_numbered_blank=False,
            blank_type=None,
        )

        self.assertEqual(
            resolve_required_blank_type(template, print_variant="guard"),
            BLANK_TYPE_GUARD_MEDICAL_CERTIFICATE,
        )
        self.assertEqual(
            resolve_required_blank_type(template, print_variant="chod"),
            BLANK_TYPE_GUARD_MEDICAL_CERTIFICATE,
        )
        self.assertIsNone(resolve_required_blank_type(template, print_variant="sport"))

    def test_xml_reuses_issued_encounter_blank_without_consuming_free_blank(self):
        with self.Session() as db:
            center = Center(code="center", name="Центр")
            client = Client(patient_number=1, last_name="Иванов", first_name="Иван", birth_date=date(1980, 2, 1))
            db.add_all([center, client])
            db.flush()
            encounter = Encounter(
                center_id=center.id,
                client_id=client.id,
                encounter_date=date(2026, 7, 13),
                payment_type="cash",
            )
            db.add(encounter)
            db.flush()
            batch = BlankBatch(
                center_id=center.id,
                blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                number_from=1,
                number_to=2,
                number_width=7,
                quantity=2,
            )
            db.add(batch)
            db.flush()
            issued = BlankForm(
                batch_id=batch.id,
                center_id=center.id,
                blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                number_value=1,
                full_number="0000001",
                status=BLANK_STATUS_ISSUED,
                client_id=client.id,
                encounter_id=encounter.id,
                issued_at=datetime(2026, 7, 13, 10, tzinfo=timezone.utc),
            )
            free = BlankForm(
                batch_id=batch.id,
                center_id=center.id,
                blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                number_value=2,
                full_number="0000002",
                status=BLANK_STATUS_FREE,
            )
            db.add_all([issued, free])
            db.flush()

            resolved = _resolve_miac_issued_blank(
                db,
                blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                client_id=client.id,
                encounter_id=encounter.id,
                center_id=center.id,
                blank_form_id=None,
            )

            self.assertEqual(resolved.id, issued.id)
            self.assertEqual(db.get(BlankForm, free.id).status, BLANK_STATUS_FREE)

    def test_gims_generation_issues_selected_free_blank(self):
        original_generated_dir = settings.generated_documents_dir
        with tempfile.TemporaryDirectory() as temp_dir:
            settings.generated_documents_dir = temp_dir
            try:
                with self.Session() as db:
                    center = Center(code="center-gims", name="Центр ГИМС")
                    client = Client(
                        patient_number=2,
                        last_name="Иванов",
                        first_name="Иван",
                        middle_name="Иванович",
                        birth_date=date(1980, 2, 1),
                        snils="123-456-789 01",
                        address_text="Санкт-Петербург, Невский проспект, д. 1",
                    )
                    db.add_all([center, client])
                    db.flush()
                    encounter = Encounter(
                        center_id=center.id,
                        client_id=client.id,
                        encounter_date=date(2026, 7, 13),
                        payment_type="cash",
                    )
                    db.add(encounter)
                    db.flush()
                    template_path = (
                        Path(__file__).resolve().parents[2]
                        / "assets"
                        / "templates"
                        / "Templates"
                        / "ГИМС_шаблон_для_загрузки_из_файла.xml"
                    )
                    template = DocumentTemplate(
                        code="gims-xml-test",
                        name="ГИМС XML",
                        file_name=template_path.name,
                        file_path=str(template_path),
                        template_type="xml",
                        output_format="xml",
                        requires_numbered_blank=True,
                        blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                        is_active=True,
                    )
                    chairman = DoctorExam(
                        client_id=client.id,
                        encounter_id=encounter.id,
                        doctor_role_id="chairman",
                        doctor_name="Петров Пётр Петрович",
                        fields_json={"conclusion": "Годен"},
                        result_text="Годен",
                        is_completed=True,
                        completed_at=datetime(2026, 7, 13, 10, 30, tzinfo=timezone.utc),
                    )
                    batch = BlankBatch(
                        center_id=center.id,
                        blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                        series="ГИМС",
                        number_from=1,
                        number_to=1,
                        number_width=7,
                        quantity=1,
                    )
                    db.add_all([template, chairman, batch])
                    db.flush()
                    blank = BlankForm(
                        batch_id=batch.id,
                        center_id=center.id,
                        blank_type=BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                        series="ГИМС",
                        number_value=1,
                        full_number="ГИМС0000001",
                        status=BLANK_STATUS_FREE,
                    )
                    db.add(blank)
                    db.flush()

                    result = generate_document(
                        db,
                        template_id=template.id,
                        template_code=None,
                        client_id=client.id,
                        encounter_id=encounter.id,
                        blank_form_id=blank.id,
                    )
                    db.commit()
                    db.refresh(blank)

                    self.assertEqual(blank.status, BLANK_STATUS_ISSUED)
                    self.assertEqual(result.blank_number, "ГИМС0000001")
                    root = ET.parse(result.output_file_path).getroot()
                    ns = {"mb": MIAC_NS}
                    self.assertEqual(root.findtext("mb:blankInfo/mb:id", namespaces=ns), "ГИМС0000001")
            finally:
                settings.generated_documents_dir = original_generated_dir


if __name__ == "__main__":
    unittest.main()
