"""Тракторная справка 071у живёт по своим категориям.

У удостоверения тракториста-машиниста категории AI, AII, AIII, AIV, B, C, D,
E, F. На любые из них идут терапевт, офтальмолог, психиатр и нарколог, на C, D
и E — ещё невролог и отоларинголог. Председатель отмечает эти категории в своей
карточке, и по ним на лицевой стороне печатаются невролог и ЛОР.

На обороте в таблице «Медицинские ограничения» по строке на категорию: там
«не установлено», пока председатель не отметит ограничение по этой категории.
Ниже, в «Медицинских показаниях», у каждого показания галочка, если
председатель его отметил, иначе Z-прочерк. Над таблицей у каждой категории
галочка, если председатель её отметил, иначе тоже Z-прочерк.
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

from app.services.document_generator import (  # noqa: E402
    _driver_certificate_lines,
    _driver_document_context_overrides,
    _exam_map,
    _generate_runtime_xls,
)
from app.services.driver_rules import (  # noqa: E402
    TRACTOR_CATEGORY_KEYS,
    is_tractor_service,
    tractor_category_tokens,
    tractor_certificate_doctor_roles,
)
from app.services.new_xls_templates import (  # noqa: E402
    TRACTOR_BACK_CATEGORY_CELLS,
    TRACTOR_BACK_INDICATION_CELLS,
    TRACTOR_BACK_RESTRICTION_CELLS,
    strip_new_xls_placeholder_padding,
)
from app.services.seed import DOCTOR_ROLES, SERVICE_DOCTOR_ROLE_IDS  # noqa: E402


TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates"
TRACTOR_SERVICE_LEGACY_ID = 7
BASE_DOCTORS = {"therapist", "ophthalmologist", "psychiatrist", "psychiatrist-narcologist"}
ALL_DOCTORS = BASE_DOCTORS | {"neurologist", "otolaryngologist"}
NOT_SET = "Не Установлено"
RESTRICTION_NOT_SET = "не\nустановлено"
TICK = "галочка"
CROSS = "Z-прочерк"
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
    def generate(self, file_name, print_variant, chairman_fields, *, chairman_completed=True):
        tractor_client = client("C D")
        exams_by_role = certificate_exams(chairman_fields)
        exams_by_role["chairman"].is_completed = chairman_completed
        exams = list(exams_by_role.values())
        # Отметки председателя попадают в контекст документа, как в generate_document.
        context = {"ClientCalc": "Проверкин Иван Иванович", **_driver_document_context_overrides(tractor_client, exams)}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / file_name
            _generate_runtime_xls(
                TEMPLATES_DIR / file_name,
                path,
                context,
                tractor_client,
                SimpleNamespace(encounter_date=date(2026, 9, 22)),
                {"exams": exams},
                print_variant=print_variant,
            )
            return xlrd.open_workbook(str(path), formatting_info=True).sheet_by_index(0)

    def test_front_follows_the_tractor_categories_of_the_chairman(self):
        rows = (35, 37, 39)
        for categories, expected in ((("AI", "B", "F"), [NOT_SET] * 3), (("B", "E"), EXTENDED_LINES)):
            with self.subTest(categories=categories):
                sheet = self.generate("трактор лиц ст.xls", "tractor_front", tractor_fields(*categories))
                actual = [strip_new_xls_placeholder_padding(sheet.cell_value(row, 12)).strip() for row in rows]
                self.assertEqual(actual, expected)

    def back_restrictions(self, chairman_fields):
        sheet = self.generate("трактор об ст.xls", "tractor_back", chairman_fields)
        return {
            category: [strip_new_xls_placeholder_padding(sheet.cell_value(*cell)) for cell in cells]
            for category, cells in TRACTOR_BACK_RESTRICTION_CELLS.items()
        }

    def test_back_prints_not_set_restrictions_on_both_halves(self):
        restrictions = self.back_restrictions(tractor_fields(*TRACTOR_CATEGORY_KEYS))
        self.assertEqual(restrictions, {category: [RESTRICTION_NOT_SET] * 2 for category in TRACTOR_CATEGORY_KEYS})

    def test_back_ignores_restrictions_saved_in_an_old_chairman_card(self):
        fields = {**tractor_fields(*TRACTOR_CATEGORY_KEYS), "tractorRestrictionC": True, "tractorRestrictionF": True}
        restrictions = self.back_restrictions(fields)
        self.assertEqual(restrictions, {category: [RESTRICTION_NOT_SET] * 2 for category in TRACTOR_CATEGORY_KEYS})

    def back_marks(self, chairman_fields, cells_to_check, *, chairman_completed=True):
        sheet = self.generate("трактор об ст.xls", "tractor_back", chairman_fields, chairman_completed=chairman_completed)

        def mark(cell):
            border = sheet.book.xf_list[sheet.cell_xf_index(*cell)].border
            if border.diag_line_style and border.top_line_style and border.bottom_line_style:
                return CROSS
            if border.diag_line_style and border.left_line_style:
                return TICK
            return ""

        return [[mark(cell) for cell in cells] for cells in cells_to_check]

    def back_indication_marks(self, chairman_fields):
        return self.back_marks(chairman_fields, TRACTOR_BACK_INDICATION_CELLS)

    def back_category_marks(self, chairman_fields, **options):
        return self.back_marks(chairman_fields, TRACTOR_BACK_CATEGORY_CELLS.values(), **options)

    def test_back_ticks_only_the_categories_the_chairman_chose(self):
        chosen = ("AI", "B", "E")
        expected = [[TICK if category in chosen else CROSS] * 2 for category in TRACTOR_CATEGORY_KEYS]
        self.assertEqual(self.back_category_marks(tractor_fields(*chosen)), expected)

    def test_back_crosses_out_the_last_category_when_it_is_not_chosen(self):
        chosen = TRACTOR_CATEGORY_KEYS[:-1]
        expected = [[TICK] * 2] * (len(TRACTOR_CATEGORY_KEYS) - 1) + [[CROSS] * 2]
        self.assertEqual(self.back_category_marks(tractor_fields(*chosen)), expected)

    def test_back_ticks_every_category_when_the_card_has_no_tractor_categories(self):
        expected = [[TICK] * 2] * len(TRACTOR_CATEGORY_KEYS)
        self.assertEqual(self.back_category_marks({"categoryB": True}), expected)

    def test_back_ticks_every_category_while_the_chairman_has_not_finished(self):
        expected = [[TICK] * 2] * len(TRACTOR_CATEGORY_KEYS)
        self.assertEqual(self.back_category_marks(tractor_fields("B"), chairman_completed=False), expected)

    def test_back_category_marks_do_not_change_the_indications(self):
        self.assertEqual(self.back_indication_marks(tractor_fields("AI")), [[CROSS, CROSS]] * 5)

    def test_back_crosses_out_indications_the_chairman_did_not_mark(self):
        self.assertEqual(self.back_indication_marks(tractor_fields("B")), [[CROSS, CROSS]] * 5)

    def test_back_ticks_each_indication_of_the_chairman_in_its_own_row(self):
        indications = ("indicationManual", "indicationAutomatic", "indicationAcoustic", "indicationGlasses", "indicationHearingAid")
        for position, field_key in enumerate(indications):
            with self.subTest(indication=field_key):
                marks = self.back_indication_marks({**tractor_fields("B"), field_key: True})
                self.assertEqual(marks, [[TICK if row == position else CROSS] * 2 for row in range(len(indications))])


if __name__ == "__main__":
    unittest.main()
