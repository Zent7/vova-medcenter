"""Нарколог должен попадать в справки 001 ГСУ и гостайны.

Строки для него в обоих шаблонах были всегда, но услуги ГС и ГТ не звали
психиатра-нарколога, поэтому осмотра не существовало и клетки оставались
пустыми. Тест закрывает обе половины: состав врачей у услуг и подстановку
ФИО в готовый файл.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

import xlrd


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.document_generator import _generate_runtime_xls  # noqa: E402
from app.services.seed import DOCTOR_ROLES, SERVICE_DOCTOR_ROLE_IDS  # noqa: E402


TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates"
NARCOLOGIST_NAME = "Нарколог Тестов"
GSU_SERVICE_LEGACY_ID = 2
GOSTAINA_SERVICE_LEGACY_ID = 11


def exam(role_id: str, doctor_name: str) -> SimpleNamespace:
    return SimpleNamespace(
        doctor_role_id=role_id,
        doctor_name=doctor_name,
        diagnosis="",
        result_text="Противопоказаний нет",
        fields_json={"objective": "Состояние удовлетворительное"},
        completed_at=datetime(2026, 9, 20, 10, 0),
        is_completed=True,
    )


def sheet_text(path: Path) -> str:
    sheet = xlrd.open_workbook(str(path)).sheet_by_index(0)
    return "\n".join(
        str(sheet.cell_value(row, col))
        for row in range(sheet.nrows)
        for col in range(sheet.ncols)
    )


class NarcologistInGsuAndGostainaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = SimpleNamespace(birth_date=date(1988, 4, 12), admission_category="")
        self.encounter = SimpleNamespace(encounter_date=date(2026, 9, 20))
        self.context = {
            "ClientCalc": "Проверкин Алексей Сергеевич",
            "AddressCalc": "г. Санкт-Петербург, Невский проспект, д. 10",
            "SexCalc": "муж",
            "SexFull": "мужской",
            "ReferenceNumber": "REF-77",
            "Conclusion": "Годен",
        }
        self.exams = [
            exam("chairman", "Председатель Тестов"),
            exam("therapist", "Терапевт Тестов"),
            exam("psychiatrist", "Психиатр Тестов"),
            exam("psychiatrist-narcologist", NARCOLOGIST_NAME),
            exam("neurologist", "Невролог Тестов"),
        ]

    def narcologist_role_legacy_id(self) -> int:
        return next(
            legacy_id
            for legacy_id, code, _, _ in DOCTOR_ROLES
            if code == "psychiatrist-narcologist"
        )

    def generate(self, file_name: str, print_variant: str) -> str:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / file_name

            _generate_runtime_xls(
                TEMPLATES_DIR / file_name,
                output_path,
                self.context,
                self.client,
                self.encounter,
                {"exams": self.exams},
                print_variant=print_variant,
            )

            return sheet_text(output_path)

    def test_gsu_service_sends_the_client_to_the_narcologist(self):
        self.assertIn(
            self.narcologist_role_legacy_id(),
            SERVICE_DOCTOR_ROLE_IDS[GSU_SERVICE_LEGACY_ID],
        )

    def test_gostaina_service_sends_the_client_to_the_narcologist(self):
        self.assertIn(
            self.narcologist_role_legacy_id(),
            SERVICE_DOCTOR_ROLE_IDS[GOSTAINA_SERVICE_LEGACY_ID],
        )

    def test_gsu_certificate_prints_the_narcologist_name(self):
        self.assertIn(NARCOLOGIST_NAME, self.generate("ГС НОВЫЙ ФОРМАТ.xls", "gsu"))

    def test_gostaina_certificate_prints_the_narcologist_name(self):
        self.assertIn(NARCOLOGIST_NAME, self.generate("ГТ.xls", "gostaina"))


if __name__ == "__main__":
    unittest.main()
