from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
import xml.etree.ElementTree as ET

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.document_generator import (  # noqa: E402
    MIAC_NS,
    SOAP_NS,
    _build_miac_driver_xml,
    _build_miac_guard_xml,
    _resolve_miac_issued_blank,
)
import app.models  # noqa: E402,F401
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

    def test_missing_completed_chairman_is_rejected_with_field_list(self):
        with self.assertRaisesRegex(ValueError, "завершённый осмотр председателя комиссии"):
            _build_miac_guard_xml(make_client(), make_blank(), [])

    def test_only_canonical_miac_xml_templates_are_active(self):
        self.assertTrue(template_is_active_by_default("Водительская(новая).xml"))
        self.assertTrue(template_is_active_by_default("Чод_новый.xml"))
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


if __name__ == "__main__":
    unittest.main()
