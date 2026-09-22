"""Тракторная справка 071у живёт по своим категориям.

У удостоверения тракториста-машиниста категории AI, AII, AIII, AIV, B, C, D,
E, F. На любые из них идут терапевт, офтальмолог, психиатр и нарколог, на C, D
и E — ещё невролог и отоларинголог. Председатель отмечает эти категории в своей
карточке, и по ним на лицевой стороне печатаются невролог и ЛОР.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

import xlrd


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.document_generator import _driver_certificate_lines, _exam_map, _generate_runtime_xls  # noqa: E402
from app.services.driver_rules import (  # noqa: E402
    TRACTOR_CATEGORY_KEYS,
    is_tractor_service,
    tractor_category_tokens,
    tractor_certificate_doctor_roles,
)
from app.services.new_xls_templates import strip_new_xls_placeholder_padding  # noqa: E402
from app.services.seed import DOCTOR_ROLES, SERVICE_DOCTOR_ROLE_IDS  # noqa: E402


TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates"
TRACTOR_SERVICE_LEGACY_ID = 7
BASE_DOCTORS = {"therapist", "ophthalmologist", "psychiatrist", "psychiatrist-narcologist"}
ALL_DOCTORS = BASE_DOCTORS | {"neurologist", "otolaryngologist"}
NOT_SET = "Не Установлено"
PSYCHIATRIST_CONCLUSION = "Психиатрических противопоказаний не выявлено"
NARCOLOGIST_CONCLUSION = "Наркологических противопоказаний не выявлено"


def exam(role, doctor_name, fields=None, *, is_completed=True):
    return SimpleNamespace(
        doctor_role_id=role,
        fields_json=fields or {},
        is_completed=is_completed,
        doctor_name=doctor_name,
        diagnosis="",
        result_text="",
        completed_at=None,
    )


def tractor_fields(*categories):
    return {f"tractorCategory{category}": category in categories for category in TRACTOR_CATEGORY_KEYS}


def client(admission_category=""):
    return SimpleNamespace(admission_category=admission_category, indications="", birth_date=date(1990, 1, 1))


def certificate_exams(chairman_fields):
    return _exam_map([
        exam("therapist", "Сибирцев Вячеслав Александрович"),
        exam("ophthalmologist", "Цыганюк Ю. С."),
        exam("neurologist", "Этчанов С."),
        exam("otolaryngologist", "Изория С. Г."),
        exam("psychiatrist", "Аносов И. Е.", {"conclusion": PSYCHIATRIST_CONCLUSION}),
        exam("psychiatrist-narcologist", "Нарколог Тестов", {"conclusion": NARCOLOGIST_CONCLUSION}),
        exam("chairman", "Председатель", chairman_fields),
    ])


EXTENDED_LINES = ["Этчанов С. Противопоказания Отсутствуют", "Изория С. Г. Противопоказания Отсутствуют", "ЭЭГ Без Патологии"]


class TractorCategoryRulesTests(unittest.TestCase):
    def test_categories_are_read_in_latin_cyrillic_and_digits(self):
        self.assertEqual(tractor_category_tokens("AI, AII, AIII, AIV, B, C, D, E, F"), set(TRACTOR_CATEGORY_KEYS))
        self.assertEqual(tractor_category_tokens("А1, A2, АIII, aiv"), {"AI", "AII", "AIII", "AIV"})
        self.assertEqual(tractor_category_tokens("В, С, Д, Е, Ф"), {"B", "C", "D", "E", "F"})
        self.assertEqual(tractor_category_tokens(["B", "E"]), {"B", "E"})

    def test_driver_only_categories_do_not_become_tractor_ones(self):
        self.assertEqual(tractor_category_tokens("M BE CE DE Tm Tb C1E D1E"), set())
        self.assertEqual(tractor_category_tokens(None), set())

    def test_base_categories_send_to_therapist_ophthalmologist_psychiatrist_and_narcologist(self):
        for categories in ("AI", "AII", "AIII", "AIV", "B", "F", "AI AII AIII AIV B F", ""):
            with self.subTest(categories=categories):
                self.assertEqual(tractor_certificate_doctor_roles(categories), BASE_DOCTORS)

    def test_c_d_and_e_add_neurologist_and_otolaryngologist(self):
        for categories in ("C", "D", "E", "B E", TRACTOR_CATEGORY_KEYS):
            with self.subTest(categories=categories):
                self.assertEqual(tractor_certificate_doctor_roles(categories), ALL_DOCTORS)

    def test_only_the_071_service_is_a_tractor_one(self):
        self.assertTrue(is_tractor_service(SimpleNamespace(legacy_source_id=7, name="071У")))
        self.assertTrue(is_tractor_service(SimpleNamespace(legacy_source_id=None, name="Тракторная")))
        self.assertFalse(is_tractor_service(SimpleNamespace(legacy_source_id=8, name="Медицинская комиссия")))
        self.assertFalse(is_tractor_service(SimpleNamespace(legacy_source_id=29, name="Водительская справка")))

    def test_071_service_sends_the_client_to_every_tractor_doctor(self):
        role_code_by_legacy_id = {legacy_id: code for legacy_id, code, _, _ in DOCTOR_ROLES}
        roles = {role_code_by_legacy_id[role_id] for role_id in SERVICE_DOCTOR_ROLE_IDS[TRACTOR_SERVICE_LEGACY_ID]}
        self.assertEqual(roles, ALL_DOCTORS)


class TractorCertificateLinesTests(unittest.TestCase):
    def test_base_tractor_categories_leave_neurologist_and_ent_unset(self):
        lines = _driver_certificate_lines(client("C D"), certificate_exams(tractor_fields("AI", "B", "F")), tractor=True)
        self.assertEqual(lines[:2], ["Сибирцев В. А. Противопоказания Отсутствуют", "Цыганюк Ю. С. Противопоказания Отсутствуют"])
        self.assertEqual(lines[2:5], [NOT_SET] * 3)

    def test_c_d_and_e_print_neurologist_ent_and_eeg(self):
        for category in ("C", "D", "E"):
            with self.subTest(category=category):
                lines = _driver_certificate_lines(client(), certificate_exams(tractor_fields("B", category)), tractor=True)
                self.assertEqual(lines[2:5], EXTENDED_LINES)

    def test_chairman_saved_before_tractor_categories_prints_as_before(self):
        old_extended = {"categoryB": True, "categoryC": True}
        old_base = {"categoryB": True, "categoryC": False}
        self.assertEqual(_driver_certificate_lines(client(), certificate_exams(old_extended), tractor=True)[2:5], EXTENDED_LINES)
        self.assertEqual(_driver_certificate_lines(client("C D"), certificate_exams(old_base), tractor=True)[2:5], [NOT_SET] * 3)

    def test_driver_certificate_ignores_tractor_categories(self):
        fields = {**tractor_fields(*TRACTOR_CATEGORY_KEYS), "categoryB": True, "categoryC": False}
        self.assertEqual(_driver_certificate_lines(client(), certificate_exams(fields))[2:5], [NOT_SET] * 3)

    def test_draft_chairman_falls_back_to_the_client_categories(self):
        exams = certificate_exams(tractor_fields("B"))
        exams["chairman"].is_completed = False
        self.assertEqual(_driver_certificate_lines(client("C"), exams, tractor=True)[2:5], EXTENDED_LINES)


class TractorFrontSheetTests(unittest.TestCase):
    def generate(self, file_name, print_variant, chairman_fields):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / file_name
            _generate_runtime_xls(
                TEMPLATES_DIR / file_name,
                path,
                {"ClientCalc": "Проверкин Иван Иванович"},
                client("C D"),
                SimpleNamespace(encounter_date=date(2026, 9, 22)),
                {"exams": list(certificate_exams(chairman_fields).values())},
                print_variant=print_variant,
            )
            return xlrd.open_workbook(str(path)).sheet_by_index(0)

    def test_front_follows_the_tractor_categories_of_the_chairman(self):
        rows = (35, 37, 39)
        for categories, expected in ((("AI", "B", "F"), [NOT_SET] * 3), (("B", "E"), EXTENDED_LINES)):
            with self.subTest(categories=categories):
                sheet = self.generate("трактор лиц ст.xls", "tractor_front", tractor_fields(*categories))
                actual = [strip_new_xls_placeholder_padding(sheet.cell_value(row, 12)).strip() for row in rows]
                self.assertEqual(actual, expected)

    def test_back_prints_psychiatrist_and_narcologist(self):
        sheet = self.generate("трактор об ст.xls", "tractor_back", tractor_fields(*TRACTOR_CATEGORY_KEYS))
        text = "\n".join(str(sheet.cell_value(row, 18)) for row in (20, 21))
        self.assertNotIn("[Психиатр", text)
        self.assertNotIn("[Нарколог", text)


if __name__ == "__main__":
    unittest.main()
