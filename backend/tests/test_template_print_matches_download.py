"""В услуге печатается тот же бланк, что лежит на странице «Шаблоны».

Заказчик скачивает шаблон, правит его в Excel и загружает обратно. Печать
должна взять именно этот файл и сохранить всё, что в нём настроено: область
печати, ориентацию, поля, масштаб и колонтитулы. Меняются только значения
полей и скрытая копия справки ВУ.
"""

from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


os.environ.setdefault("ALLOW_SQLITE", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.document_template import DocumentTemplate  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.services.document_generator import (  # noqa: E402
    _generate_runtime_xls,
    _new_xls_workbook_stream,
    _write_new_xls_stream_bytes,
    generate_document,
)
from app.services.new_xls_templates import NEW_XLS_TEMPLATE_SPECS  # noqa: E402
from app.services.template_catalog import resolve_template_file  # noqa: E402


TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates"
DRIVER_FRONT_FILE_NAME = "водительская лицевая.xls"

# Как печатает услуга: вариант печати для каждого бланка со свободным макетом.
SERVICE_PRINT_VARIANTS: tuple[tuple[str, str | None], ...] = (
    *((spec.file_name, spec.print_variant) for spec in NEW_XLS_TEMPLATE_SPECS),
    (DRIVER_FRONT_FILE_NAME, "driver_front"),
    ("водительская обратн ст.xls", "driver_back"),
    ("Выписка из Амб карты (профа).xls", "ambulatory_extract"),
    ("АМБ_карты_профосмотр_шаблон.xls", "prof_ambulatory"),
    ("Справка_342н_псих_освид.xls", None),
    ("ПРОФОСМОТР 29Н.xls", None),
)

_PAGE_SETUP_RECORDS = {
    0x0014: "header",
    0x0015: "footer",
    0x0026: "left_margin",
    0x0027: "right_margin",
    0x0028: "top_margin",
    0x0029: "bottom_margin",
    0x0081: "fit_to_page_flags",
    0x0083: "center_horizontally",
    0x0084: "center_vertically",
    0x00A1: "page_setup",
}
_TOP_MARGIN_RECORD = 0x0028
_NAME_RECORD = 0x0018
_BOF_RECORD = 0x0809
_EOF_RECORD = 0x000A


def _records(stream: bytes):
    offset = 0
    while offset + 4 <= len(stream):
        record_id, length = struct.unpack_from("<HH", stream, offset)
        yield record_id, offset + 4, stream[offset + 4 : offset + 4 + length]
        offset += 4 + length


def _print_area_formula_offset(payload_start: int, payload: bytes) -> int | None:
    options, _, name_length, formula_length = struct.unpack_from("<HBBH", payload)
    if not options & 0x0020 or name_length != 1 or payload[15] != 0x06 or formula_length != 11:
        return None
    return payload_start + 15 + name_length * (2 if payload[14] & 0x01 else 1)


def page_setup(path: Path) -> dict[str, bytes]:
    """Записи BIFF, от которых зависит, как лист ляжет на бумагу."""
    stream, _ = _new_xls_workbook_stream(path.read_bytes())
    result: dict[str, bytes] = {}
    substream = -1
    for record_id, payload_start, payload in _records(stream):
        if record_id == _BOF_RECORD:
            substream += 1
        elif substream == 0 and record_id == _NAME_RECORD:
            formula_offset = _print_area_formula_offset(payload_start, payload)
            if formula_offset is not None:
                result["print_area"] = stream[formula_offset : formula_offset + 11]
        elif substream == 1 and record_id in _PAGE_SETUP_RECORDS:
            result[_PAGE_SETUP_RECORDS[record_id]] = payload
    return result


def print_area_columns(path: Path) -> tuple[int, int]:
    formula = page_setup(path)["print_area"]
    first_col, last_col = struct.unpack_from("<HH", formula, 7)
    return first_col & 0x3FFF, last_col & 0x3FFF


def top_margin(path: Path) -> float:
    return struct.unpack("<d", page_setup(path)["top_margin"])[0]


def patch_customer_copy(path: Path, *, top_margin_inches: float | None = None, print_area_last_col: int | None = None) -> None:
    """Правка, какую заказчик делает в Excel: поля страницы и область печати."""
    original = path.read_bytes()
    file_bytes = bytearray(original)
    stream, sectors = _new_xls_workbook_stream(original)
    substream = -1
    for record_id, payload_start, payload in _records(stream):
        if record_id == _BOF_RECORD:
            substream += 1
        elif substream == 0 and record_id == _NAME_RECORD and print_area_last_col is not None:
            formula_offset = _print_area_formula_offset(payload_start, payload)
            if formula_offset is not None:
                _write_new_xls_stream_bytes(file_bytes, sectors, formula_offset + 9, struct.pack("<H", print_area_last_col))
        elif substream == 1 and record_id == _TOP_MARGIN_RECORD and top_margin_inches is not None:
            _write_new_xls_stream_bytes(file_bytes, sectors, payload_start, struct.pack("<d", top_margin_inches))
        elif record_id == _EOF_RECORD and substream >= 1:
            break
    path.write_bytes(file_bytes)


def service_context() -> dict[str, str]:
    return {
        "ClientCalc": "Проверкин Алексей Сергеевич",
        "LastName": "Проверкин",
        "FirstName": "Алексей",
        "MiddleName": "Сергеевич",
        "BirthDateCalc_DAY": "12",
        "BirthDateCalc_DATEMONTH": "апреля",
        "BirthDateCalc_YEAR": "1988",
        "CityCalc": "Санкт-Петербург",
        "StreetCalc": "Невский проспект",
        "HouseNumberCalc": "10",
        "ApartmentNumberCalc": "15",
        "BlankNumber": "7654321",
        "ReferenceNumber": "7654321",
    }


def generate_like_the_service(template_path: Path, output_path: Path, print_variant: str | None) -> None:
    _generate_runtime_xls(
        template_path,
        output_path,
        service_context(),
        SimpleNamespace(birth_date=date(1988, 4, 12), admission_category="B", indications="", sex="M"),
        SimpleNamespace(encounter_date=date(2026, 9, 21)),
        {"exams": [], "service_names": []},
        print_variant=print_variant,
    )


class FreeLayoutPrintKeepsTemplatePageSetupTests(unittest.TestCase):
    def test_every_free_layout_blank_prints_with_the_page_setup_of_its_template(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            for file_name, print_variant in SERVICE_PRINT_VARIANTS:
                with self.subTest(file_name=file_name, print_variant=print_variant):
                    template_path = TEMPLATES_DIR / file_name
                    output_path = Path(temporary_dir) / f"printed-{print_variant or 'plain'}-{file_name}"

                    generate_like_the_service(template_path, output_path, print_variant)

                    expected = page_setup(template_path)
                    self.assertIn("page_setup", expected)
                    self.assertEqual(page_setup(output_path), expected)

    def test_driver_certificate_follows_the_customer_margins_and_prints_only_its_left_half(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            customer_copy = Path(temporary_dir) / DRIVER_FRONT_FILE_NAME
            shutil.copy2(TEMPLATES_DIR / DRIVER_FRONT_FILE_NAME, customer_copy)
            # Заказчик опустил справку на полтора сантиметра и растянул область
            # печати на обе половины листа, как было в старом шаблоне.
            patch_customer_copy(customer_copy, top_margin_inches=1.5 / 2.54, print_area_last_col=51)
            output_path = Path(temporary_dir) / "printed.xls"

            generate_like_the_service(customer_copy, output_path, "driver_front")

            self.assertAlmostEqual(top_margin(output_path), 1.5 / 2.54)
            customer_setup = page_setup(customer_copy)
            printed_setup = page_setup(output_path)
            for key in ("page_setup", "left_margin", "header", "footer", "fit_to_page_flags"):
                self.assertEqual(printed_setup[key], customer_setup[key], key)
            # Правую копию справки печать прячет; в области печати она дала бы
            # пустые страницы.
            self.assertEqual(print_area_columns(output_path), (0, 26))

    def test_a_print_variant_for_the_other_side_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            with self.assertRaisesRegex(ValueError, "Водительская Оборотная"):
                generate_like_the_service(
                    TEMPLATES_DIR / DRIVER_FRONT_FILE_NAME,
                    Path(temporary_dir) / "printed.xls",
                    "driver_back",
                )


class PrintUsesTheDownloadedFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        root = Path(self.temporary_directory.name)
        self.overrides_dir = root / "template-overrides"
        self.generated_dir = root / "generated"
        self.overrides_dir.mkdir()
        original_overrides_dir = settings.document_template_overrides_dir
        original_generated_dir = settings.generated_documents_dir
        settings.document_template_overrides_dir = str(self.overrides_dir)
        settings.generated_documents_dir = str(self.generated_dir)
        self.addCleanup(setattr, settings, "document_template_overrides_dir", original_overrides_dir)
        self.addCleanup(setattr, settings, "generated_documents_dir", original_generated_dir)

    def tearDown(self) -> None:
        self.engine.dispose()

    def print_side(self, file_name: str, print_variant: str, patient_number: int) -> tuple[Path, Path]:
        """Печать стороны справки, когда каталог ещё помнит встроенный файл."""
        with Session(self.engine) as db:
            center = Center(code=f"center-{print_variant}", name="Медцентр")
            client = Client(
                patient_number=patient_number,
                last_name="Проверкин",
                first_name="Алексей",
                middle_name="Сергеевич",
                birth_date=date(1988, 4, 12),
                sex="M",
                admission_category="B",
            )
            db.add_all([center, client])
            db.flush()
            encounter = Encounter(
                center_id=center.id,
                client_id=client.id,
                encounter_date=date(2026, 9, 21),
                payment_type="cash",
            )
            template = DocumentTemplate(
                code=f"{print_variant}-test",
                name=file_name,
                file_name=file_name,
                file_path=str(TEMPLATES_DIR / file_name),
                template_type="xls",
                output_format="xls",
                is_active=True,
            )
            db.add_all([encounter, template])
            db.commit()

            downloaded_path = resolve_template_file(template)
            result = generate_document(
                db,
                template_id=template.id,
                template_code=None,
                client_id=client.id,
                encounter_id=encounter.id,
                print_variant=print_variant,
            )
        return downloaded_path, Path(result.output_file_path)

    def test_print_takes_the_customer_copy_even_when_the_catalog_path_is_stale(self):
        for patient_number, (file_name, print_variant) in enumerate(
            ((DRIVER_FRONT_FILE_NAME, "driver_front"), ("трактор об ст.xls", "tractor_back")),
            start=1,
        ):
            with self.subTest(file_name=file_name):
                customer_copy = self.overrides_dir / file_name
                shutil.copy2(TEMPLATES_DIR / file_name, customer_copy)
                patch_customer_copy(customer_copy, top_margin_inches=1.0)
                self.assertNotAlmostEqual(top_margin(TEMPLATES_DIR / file_name), 1.0)

                downloaded_path, printed_path = self.print_side(file_name, print_variant, patient_number)

                self.assertEqual(downloaded_path, customer_copy.resolve())
                self.assertAlmostEqual(top_margin(printed_path), 1.0)


if __name__ == "__main__":
    unittest.main()
