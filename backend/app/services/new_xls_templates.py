from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import xlrd


Cell = tuple[int, int]
PLACEHOLDER_LENGTH = 240
PLACEHOLDER_ZERO = "\u200b"
PLACEHOLDER_ONE = "\u200c"
PLACEHOLDER_JOIN = "\u200d"
PLACEHOLDER_START = f"{PLACEHOLDER_ZERO}{PLACEHOLDER_ONE}{PLACEHOLDER_JOIN}{PLACEHOLDER_ONE}"
PLACEHOLDER_END = f"{PLACEHOLDER_ONE}{PLACEHOLDER_JOIN}{PLACEHOLDER_ONE}{PLACEHOLDER_ZERO}"
PLACEHOLDER_FILL = PLACEHOLDER_ZERO
OLD_PLACEHOLDER_START = "\u2060"
OLD_PLACEHOLDER_END = "\u2063"
PLACEHOLDER_LABEL_OPEN = "["
PLACEHOLDER_LABEL_CLOSE = "]"


def _row_cells(row: int, start_col: int, end_col: int) -> tuple[Cell, ...]:
    return tuple((row, col) for col in range(start_col, end_col + 1))


@dataclass(frozen=True)
class NewXlsTemplateSpec:
    file_name: str
    sheet_name: str
    print_variant: str
    print_pages_tall: int
    dynamic_cells: tuple[Cell, ...]
    source_file_name: str = ""
    print_pages_wide: int = 1
    print_area: str = ""
    print_zoom: int | None = None
    vertical_page_break_column: int | None = None


@dataclass(frozen=True)
class LegacyXlsField:
    field_id: str
    sheet_name: str
    source_cell: Cell


@dataclass(frozen=True)
class LegacyXlsTemplateSpec:
    file_name: str
    sheet_names: tuple[str, ...]
    fields: tuple[LegacyXlsField, ...]


# Coordinates are zero-based. Every cell below contains data that belongs to a
# patient, encounter, numbered blank, examination, or signing doctor. Static
# organization details and the prescribed form text intentionally remain intact.
NEW_XLS_TEMPLATE_SPECS: tuple[NewXlsTemplateSpec, ...] = (
    NewXlsTemplateSpec(
        file_name="ГС НОВЫЙ ФОРМАТ.xls",
        sheet_name="ГС",
        print_variant="gsu",
        print_pages_tall=1,
        print_pages_wide=2,
        vertical_page_break_column=30,
        dynamic_cells=(
            (4, 38),
            (6, 39),
            (6, 52),
            (7, 47),
            (18, 9),
            (18, 19),
            (19, 38),
            (21, 39),
            (21, 52),
            (22, 47),
            (27, 11),
            (30, 14),
            (31, 10),
            (33, 2),
            (38, 26),
            (41, 26),
        ),
    ),
    NewXlsTemplateSpec(
        file_name="СКК 070 новый формат.xls",
        sheet_name="CKK",
        print_variant="070",
        print_pages_tall=2,
        dynamic_cells=(
            (12, 20),
            (14, 12),
            (18, 15),
            (19, 7),
            (19, 27),
            (21, 1),
            *_row_cells(25, 15, 30),
            (29, 20),
            (29, 21),
            (33, 20),
            (36, 3),
            (36, 8),
            (36, 20),
            (36, 33),
            *_row_cells(37, 16, 29),
            (39, 11),
            (42, 1),
            (50, 10),
            (52, 7),
            (56, 22),
            (57, 22),
        ),
    ),
    NewXlsTemplateSpec(
        file_name="СКК 72 новый формат.xls",
        sheet_name="CKK72",
        print_variant="072",
        print_pages_tall=6,
        print_area="$A$1:$AL$120",
        print_zoom=100,
        dynamic_cells=(
            (12, 24),
            (13, 12),
            (15, 14),
            (16, 7),
            (16, 24),
            (18, 1),
            *_row_cells(21, 22, 37),
            (25, 20),
            (29, 20),
            (32, 3),
            (32, 8),
            (32, 20),
            (32, 33),
            *_row_cells(33, 14, 27),
            (39, 14),
            (42, 14),
            (45, 1),
            (56, 1),
            (58, 1),
            (62, 1),
            (68, 1),
            (75, 1),
            (78, 1),
            (83, 17),
            (84, 28),
            (87, 16),
            (89, 1),
            (90, 28),
        ),
    ),
    NewXlsTemplateSpec(
        file_name="СПОРТ.xls",
        sheet_name="Спорт",
        print_variant="sport",
        print_pages_tall=1,
        dynamic_cells=(
            (1, 13),
            (12, 8),
            (13, 3),
            (13, 13),
            (15, 5),
            (19, 7),
            (22, 2),
            (23, 3),
            (27, 11),
            (29, 7),
        ),
    ),
    NewXlsTemplateSpec(
        file_name="ГТ.xls",
        sheet_name="ГТ",
        print_variant="gostaina",
        print_pages_tall=1,
        dynamic_cells=(
            (16, 6),
            (16, 11),
            (22, 2),
            (24, 4),
            (26, 4),
            (29, 0),
            (36, 9),
            (36, 15),
            (38, 9),
            (38, 15),
            (40, 9),
            (40, 15),
            (47, 11),
            (51, 15),
            (53, 15),
            (55, 15),
        ),
    ),
    NewXlsTemplateSpec(
        file_name="трактор лиц ст.xls",
        source_file_name="Для трактора.xls",
        sheet_name="Тр.Лиц",
        print_variant="tractor_front",
        print_pages_tall=1,
        print_area="$A$1:$AZ$42",
        print_zoom=97,
        dynamic_cells=(
            (7, 3),
            (7, 30),
            (14, 2),
            (14, 28),
            (15, 8),
            (15, 15),
            (15, 22),
            (15, 35),
            (15, 41),
            (15, 48),
            (17, 12),
            (17, 38),
            (18, 4),
            (18, 31),
            (19, 6),
            (19, 32),
            (20, 2),
            (20, 30),
            (21, 2),
            (21, 29),
            (22, 2),
            (22, 9),
            (22, 29),
            (22, 36),
            (23, 12),
            (23, 39),
            (26, 2),
            (26, 11),
            (26, 21),
            (26, 29),
            (26, 38),
            (26, 47),
            (29, 12),
            (29, 39),
            (31, 12),
            (31, 39),
            (35, 12),
            (35, 39),
            (37, 12),
            (37, 39),
        ),
    ),
    NewXlsTemplateSpec(
        file_name="трактор об ст.xls",
        sheet_name="Тр.Об",
        print_variant="tractor_back",
        print_pages_tall=1,
        dynamic_cells=(
            (9, 18),
            (9, 38),
            (11, 18),
            (11, 38),
            (14, 18),
            (14, 38),
            (17, 18),
            (17, 38),
            (19, 18),
            (19, 38),
            (20, 18),
            (20, 38),
            (21, 18),
            (21, 38),
            (22, 18),
            (22, 38),
            (23, 18),
            (23, 38),
            (36, 5),
            (36, 25),
        ),
    ),
    NewXlsTemplateSpec(
        file_name="ГИМС (судна).xls",
        sheet_name="Суда",
        print_variant="gims",
        print_pages_tall=1,
        dynamic_cells=(
            (7, 3),
            (7, 30),
            (14, 2),
            (14, 28),
            (15, 14),
            (15, 17),
            (15, 21),
            (15, 39),
            (15, 42),
            (15, 46),
            (17, 3),
            (17, 29),
            (18, 17),
            (18, 43),
            (19, 4),
            (19, 32),
            (20, 7),
            (20, 35),
            (21, 4),
            (21, 20),
            (21, 31),
            (21, 47),
            (22, 8),
            (22, 17),
            (22, 34),
            (22, 41),
            (34, 15),
            (34, 19),
            (34, 23),
            (34, 39),
            (34, 44),
            (34, 48),
            (36, 9),
            (36, 31),
        ),
    ),
    NewXlsTemplateSpec(
        file_name="ЛМК.xls",
        sheet_name=" ЛМК!",
        print_variant="lmk",
        print_pages_tall=1,
        print_area="$A$1:$X$30",
        print_zoom=100,
        dynamic_cells=(
            (10, 5),
            (12, 5),
            (15, 5),
            (17, 5),
            (21, 1),
            (25, 4),
            (28, 0),
        ),
    ),
)


NEW_XLS_TEMPLATE_BY_SHEET = {spec.sheet_name: spec for spec in NEW_XLS_TEMPLATE_SPECS}
NEW_XLS_TEMPLATE_BY_FILE = {spec.file_name.casefold(): spec for spec in NEW_XLS_TEMPLATE_SPECS}


def _indexed_labels(prefix: str, cells: tuple[Cell, ...]) -> dict[Cell, str]:
    return {cell: f"{prefix} {index}" for index, cell in enumerate(cells, start=1)}


def _sided_labels(items: tuple[tuple[str, Cell, Cell], ...]) -> dict[Cell, str]:
    """Label the two identical halves printed on one certificate blank."""
    return {
        cell: f"{label} ({side})"
        for label, left_cell, right_cell in items
        for side, cell in (("лев", left_cell), ("прав", right_cell))
    }


# Every dynamic cell carries a readable label so the customer sees «[ФИО]»
# instead of an invisible marker and can move the field around in Excel.
NEW_XLS_FIELD_LABELS: dict[str, dict[Cell, str]] = {
    "ГС НОВЫЙ ФОРМАТ.xls": {
        (4, 38): "Нарколог заключение",
        (6, 39): "Нарколог должность",
        (6, 52): "Нарколог ФИО",
        (7, 47): "Нарколог результаты",
        (18, 9): "Дата выдачи",
        (18, 19): "Номер бланка",
        (19, 38): "Психиатр заключение",
        (21, 39): "Психиатр должность",
        (21, 52): "Психиатр ФИО",
        (22, 47): "Психиатр результаты",
        (27, 11): "ФИО",
        (30, 14): "Пол",
        (31, 10): "Дата рождения",
        (33, 2): "Адрес",
        (38, 26): "Терапевт",
        (41, 26): "Подписант",
    },
    "СКК 070 новый формат.xls": {
        (12, 20): "Номер бланка",
        (14, 12): "Дата выдачи",
        (18, 15): "ФИО",
        (19, 7): "Дата рождения",
        (19, 27): "Пол",
        (21, 1): "Адрес",
        **_indexed_labels("ОМС", _row_cells(25, 15, 30)),
        (29, 20): "Код инвалидности",
        (29, 21): "Код льготы",
        (33, 20): "Вид страхования",
        (36, 3): "Серия документа",
        (36, 8): "Номер документа",
        (36, 20): "Дата документа",
        (36, 33): "Телефон",
        **_indexed_labels("СНИЛС", _row_cells(37, 16, 29)),
        (39, 11): "Санаторий",
        (42, 1): "Диагноз",
        (50, 10): "Вид лечения",
        (52, 7): "Место лечения",
        (56, 22): "Терапевт",
        (57, 22): "Подписант",
    },
    "СКК 72 новый формат.xls": {
        (12, 24): "Номер бланка",
        (13, 12): "Дата выдачи",
        (15, 14): "ФИО",
        (16, 7): "Дата рождения",
        (16, 24): "Пол",
        (18, 1): "Адрес",
        **_indexed_labels("ОМС", _row_cells(21, 22, 37)),
        (25, 20): "Код льготы",
        (29, 20): "Вид страхования",
        (32, 3): "Серия документа",
        (32, 8): "Номер документа",
        (32, 20): "Дата документа",
        (32, 33): "Телефон",
        **_indexed_labels("СНИЛС", _row_cells(33, 14, 27)),
        (39, 14): "Санаторий",
        (42, 14): "ФИО повтор",
        (45, 1): "Диагноз",
        (56, 1): "Жалобы",
        (58, 1): "Анамнез",
        (62, 1): "Результаты обследования",
        (68, 1): "Диагноз повтор",
        (75, 1): "Дополнительные сведения",
        (78, 1): "Причина инвалидности",
        (83, 17): "Санаторий повтор",
        (84, 28): "Вид лечения",
        (87, 16): "Номер путёвки",
        (89, 1): "Врач",
        (90, 28): "Подписант",
    },
    "СПОРТ.xls": {
        (1, 13): "Номер бланка",
        (12, 8): "Дата выдачи",
        (13, 3): "ФИО",
        (13, 13): "Дата рождения",
        (15, 5): "Дата осмотра",
        (19, 7): "Вид спорта",
        (22, 2): "ЭКГ",
        (23, 3): "Заключение",
        (27, 11): "Подписант",
        (29, 7): "Действительна до",
    },
    "ГТ.xls": {
        (16, 6): "Дата выдачи",
        (16, 11): "Номер бланка",
        (22, 2): "ФИО",
        (24, 4): "Дата рождения",
        (26, 4): "Пол",
        (29, 0): "Адрес",
        (36, 9): "Нарколог дата",
        (36, 15): "Нарколог ФИО",
        (38, 9): "Психиатр дата",
        (38, 15): "Психиатр ФИО",
        (40, 9): "Невролог дата",
        (40, 15): "Невролог ФИО",
        (47, 11): "Подписант",
        (51, 15): "Невролог подпись",
        (53, 15): "Нарколог подпись",
        (55, 15): "Психиатр подпись",
    },
    "трактор лиц ст.xls": _sided_labels(
        (
            ("Номер бланка", (7, 3), (7, 30)),
            ("ФИО", (14, 2), (14, 28)),
            ("День рождения", (15, 8), (15, 35)),
            ("Месяц рождения", (15, 15), (15, 41)),
            ("Год рождения", (15, 22), (15, 48)),
            ("Регион", (17, 12), (17, 38)),
            ("Район", (18, 4), (18, 31)),
            ("Город", (19, 6), (19, 32)),
            ("Улица", (20, 2), (20, 30)),
            ("Дом", (21, 2), (21, 29)),
            ("Корпус", (22, 2), (22, 29)),
            ("Квартира", (22, 9), (22, 36)),
            ("СНИЛС", (23, 12), (23, 39)),
            ("День выдачи", (26, 2), (26, 29)),
            ("Месяц выдачи", (26, 11), (26, 38)),
            ("Год выдачи", (26, 21), (26, 47)),
            ("Терапевт", (29, 12), (29, 39)),
            ("Окулист", (31, 12), (31, 39)),
            ("Невролог", (35, 12), (35, 39)),
            ("ЛОР", (37, 12), (37, 39)),
        )
    ),
    "трактор об ст.xls": _sided_labels(
        (
            ("Терапевт", (9, 18), (9, 38)),
            ("Окулист", (11, 18), (11, 38)),
            ("Невролог", (14, 18), (14, 38)),
            ("ЛОР", (17, 18), (17, 38)),
            ("Хирург", (19, 18), (19, 38)),
            ("Психиатр", (20, 18), (20, 38)),
            ("Нарколог", (21, 18), (21, 38)),
            ("Гинеколог", (22, 18), (22, 38)),
            ("Дерматолог", (23, 18), (23, 38)),
            ("Подписант", (36, 5), (36, 25)),
        )
    ),
    "ГИМС (судна).xls": _sided_labels(
        (
            ("Номер бланка", (7, 3), (7, 30)),
            ("ФИО", (14, 2), (14, 28)),
            ("День рождения", (15, 14), (15, 39)),
            ("Месяц рождения", (15, 17), (15, 42)),
            ("Год рождения", (15, 21), (15, 46)),
            ("СНИЛС", (17, 3), (17, 29)),
            ("Регион", (18, 17), (18, 43)),
            ("Район", (19, 4), (19, 32)),
            ("Город", (20, 7), (20, 35)),
            ("Улица", (21, 4), (21, 31)),
            ("Дом", (21, 20), (21, 47)),
            ("Корпус", (22, 8), (22, 34)),
            ("Квартира", (22, 17), (22, 41)),
            ("День выдачи", (34, 15), (34, 39)),
            ("Месяц выдачи", (34, 19), (34, 44)),
            ("Год выдачи", (34, 23), (34, 48)),
            ("Подписант", (36, 9), (36, 31)),
        )
    ),
    "ЛМК.xls": {
        (10, 5): "Фамилия",
        (12, 5): "Имя и отчество",
        (15, 5): "Дата рождения",
        (17, 5): "Город",
        (21, 1): "Адрес",
        (25, 4): "Должность",
        (28, 0): "Организация",
    },
}


def _legacy_fields(sheet_name: str, items: tuple[tuple[str, Cell], ...]) -> tuple[LegacyXlsField, ...]:
    return tuple(LegacyXlsField(field_id, sheet_name, cell) for field_id, cell in items)


_DRIVER_FRONT_FIELDS = _legacy_fields(
    "Водительская Лицевая",
    (
        ("patient_name_left", (15, 2)), ("patient_name_right", (15, 28)),
        ("birth_day_left", (16, 8)), ("birth_month_left", (16, 15)), ("birth_year_left", (16, 22)),
        ("birth_day_right", (16, 35)), ("birth_month_right", (16, 41)), ("birth_year_right", (16, 48)),
        ("subject_left", (18, 9)), ("subject_right", (18, 36)),
        ("district_left", (19, 4)), ("district_right", (19, 31)),
        ("city_left", (20, 4)), ("city_right", (20, 30)),
        ("street_left", (21, 2)), ("house_left", (21, 18)),
        ("street_right", (21, 30)), ("house_right", (21, 45)),
        ("building_left", (22, 3)), ("apartment_left", (22, 12)),
        ("building_right", (22, 31)), ("apartment_right", (22, 38)),
        ("issue_day_left", (23, 15)), ("issue_month_left", (23, 19)), ("issue_year_left", (23, 23)),
        ("issue_day_right", (23, 41)), ("issue_month_right", (23, 45)), ("issue_year_right", (23, 49)),
        ("therapist_left", (28, 12)), ("therapist_right", (28, 39)),
        ("ophthalmologist_left", (30, 12)), ("ophthalmologist_right", (30, 39)),
        ("neurologist_left", (35, 12)), ("neurologist_right", (35, 39)),
        ("otolaryngologist_left", (37, 12)), ("otolaryngologist_right", (37, 39)),
        ("instrumental_left", (39, 12)), ("instrumental_right", (39, 39)),
        ("laboratory_left", (41, 12)), ("laboratory_right", (41, 39)),
    ),
)

_DRIVER_CATEGORY_KEYS = ("a", "b", "c", "d", "be", "ce", "de", "tm", "tb", "m", "a1", "b1", "c1", "d1", "c1e", "d1e")
_DRIVER_CATEGORY_LEFT = tuple((10, col) for col in range(2, 34, 2))
_DRIVER_CATEGORY_RIGHT = tuple((10, col) for col in range(35, 67, 2))
_DRIVER_BACK_FIELDS = tuple(
    LegacyXlsField(f"category_{side}_{key}", "Водительская Оборотная", cell)
    for side, cells in (("left", _DRIVER_CATEGORY_LEFT), ("right", _DRIVER_CATEGORY_RIGHT))
    for key, cell in zip(_DRIVER_CATEGORY_KEYS, cells)
) + _legacy_fields(
    "Водительская Оборотная",
    tuple(
        (f"restriction_{row}_{col}", (row, col))
        for row in (14, 17, 20, 25, 27, 29, 31, 33)
        for col in (29, 62)
    ) + (("chairman_left", (36, 8)), ("chairman_right", (36, 41))),
)

_AMB_HEADER_FIELDS = _legacy_fields(
    "Амб",
    (
        ("blank_number", (15, 54)), ("visit_date", (16, 47)), ("patient_name", (17, 43)),
        ("sex", (18, 35)), ("birth_date", (18, 48)), ("subject", (19, 54)),
        ("district", (20, 35)), ("city", (20, 49)), ("locality", (21, 40)),
        ("street", (22, 35)), ("phone", (22, 56)), ("residence_type", (23, 48)),
        ("oms_series", (24, 35)), ("oms_number", (24, 46)), ("snils", (24, 55)),
        ("document_type", (26, 48)), ("document_series", (26, 56)), ("document_number", (26, 59)),
        ("workplace", (38, 44)), ("blood_group", (47, 40)), ("rh_factor", (47, 54)),
        ("allergies", (48, 44)),
    ),
)

_AMB_BLOCK_CELLS = (
    ((1, 23), (2, 10), (3, 10), (4, 13), (6, 1), (9, 1), (14, 11)),
    ((15, 23), (16, 10), (17, 10), (18, 13), (20, 1), (23, 1), (28, 11)),
    ((51, 24), (52, 10), (53, 10), (54, 13), (56, 1), (59, 1), (64, 11)),
    ((51, 55), (52, 41), (53, 41), (54, 44), (56, 32), (59, 32), (64, 42)),
    ((66, 24), (67, 10), (68, 10), (69, 13), (71, 1), (74, 1), (79, 11)),
    ((66, 55), (67, 41), (68, 41), (69, 42), (71, 32), (74, 32), (79, 42)),
    ((81, 24), (82, 10), (83, 10), (84, 13), (86, 1), (89, 1), (94, 11)),
    ((81, 55), (82, 41), (83, 41), (84, 44), (86, 32), (89, 32), (94, 42)),
    ((96, 24), (97, 10), (98, 10), (99, 13), (101, 1), (104, 1), (109, 11)),
    ((96, 55), (97, 41), (98, 41), (99, 44), (101, 32), (104, 32), (109, 42)),
)
_AMB_BLOCK_KEYS = ("date", "title", "complaints", "anamnesis", "objective", "diagnosis", "doctor")
_AMB_BLOCK_FIELDS = tuple(
    LegacyXlsField(f"exam_{slot}_{key}", "Амб", cell)
    for slot, cells in enumerate(_AMB_BLOCK_CELLS, start=1)
    for key, cell in zip(_AMB_BLOCK_KEYS, cells)
)

_PZ2_HEADER_FIELDS = _legacy_fields(
    "ПЗ2",
    (
        ("blank_preliminary", (10, 39)), ("date_preliminary", (10, 42)),
        ("blank_periodic", (17, 31)), ("date_periodic", (17, 42)), ("issue_date", (18, 14)),
        ("last_name", (20, 8)), ("first_name", (21, 4)), ("patronymic", (21, 23)),
        ("sex", (22, 6)), ("birth_date", (22, 24)), ("address", (28, 1)), ("phone", (31, 30)),
        ("company", (35, 11)), ("company_repeat", (38, 26)), ("department", (41, 17)),
        ("position", (44, 2)), ("harmfulness", (49, 1)), ("position_repeat", (71, 42)),
        ("harmfulness_repeat", (74, 42)), ("signer", (78, 73)),
    ),
)
_PZ2_DOCTOR_ROWS = (32, 34, 37, 39, 41, 43, 45, 48, 50, 52)
_PZ2_DOCTOR_FIELDS = tuple(
    LegacyXlsField(f"doctor_{slot}_{key}", "ПЗ2", (row, col))
    for slot, row in enumerate(_PZ2_DOCTOR_ROWS, start=1)
    for key, col in (("sequence", 42), ("name", 44), ("date", 54), ("conclusion", 63))
)

_PROF2_FIELDS = _legacy_fields(
    "Проф2",
    (
        ("reference_date", (4, 29)), ("patient_name", (8, 6)), ("birth_and_sex", (10, 1)),
        ("address", (11, 1)), ("company", (14, 10)), ("examination_date", (21, 17)),
        ("position", (28, 1)), ("harmfulness", (30, 1)), ("signature_date", (39, 2)),
    ),
)

_PROF_CONCLUSION_29N_FIELDS = _legacy_fields(
    "ПРОФОСМОТР",
    (
        ("blank_number", (10, 26)), ("narcologist", (12, 42)),
        ("patient_name", (20, 5)), ("sex", (21, 6)), ("birth_date", (21, 15)),
        ("workplace", (22, 6)), ("company", (23, 9)), ("department", (25, 6)),
        ("position", (27, 13)), ("psychiatrist", (27, 42)),
        ("harmfulness", (30, 2)), ("health_group", (33, 14)),
        ("chairman", (38, 18)), ("position_repeat", (41, 1)),
        ("occupational_doctor", (42, 18)), ("issue_date", (44, 3)),
    ),
)

LEGACY_XLS_TEMPLATE_SPECS: tuple[LegacyXlsTemplateSpec, ...] = (
    LegacyXlsTemplateSpec("водительская лицевая.xls", ("Водительская Лицевая",), _DRIVER_FRONT_FIELDS),
    LegacyXlsTemplateSpec("водительская обратн ст.xls", ("Водительская Оборотная",), _DRIVER_BACK_FIELDS),
    LegacyXlsTemplateSpec("АМБ_карты_профосмотр_шаблон.xls", ("Амб",), _AMB_HEADER_FIELDS + _AMB_BLOCK_FIELDS),
    LegacyXlsTemplateSpec("Выписка из Амб карты (профа).xls", ("ПЗ2",), _PZ2_HEADER_FIELDS + _PZ2_DOCTOR_FIELDS),
    LegacyXlsTemplateSpec("Справка_342н_псих_освид.xls", ("Проф2",), _PROF2_FIELDS),
    LegacyXlsTemplateSpec("ПРОФОСМОТР 29Н.xls", ("ПРОФОСМОТР",), _PROF_CONCLUSION_29N_FIELDS),
)
LEGACY_XLS_TEMPLATE_BY_FILE = {spec.file_name.casefold(): spec for spec in LEGACY_XLS_TEMPLATE_SPECS}


def _sided_field_labels(base_labels: dict[str, str]) -> dict[str, str]:
    return {
        f"{field_id}_{side}": f"{label} ({side_name})"
        for field_id, label in base_labels.items()
        for side, side_name in (("left", "лев"), ("right", "прав"))
    }


_DRIVER_FRONT_LABELS = _sided_field_labels(
    {
        "patient_name": "ФИО",
        "birth_day": "День рождения",
        "birth_month": "Месяц рождения",
        "birth_year": "Год рождения",
        "subject": "Регион",
        "district": "Район",
        "city": "Город",
        "street": "Улица",
        "house": "Дом",
        "building": "Корпус",
        "apartment": "Квартира",
        "issue_day": "День выдачи",
        "issue_month": "Месяц выдачи",
        "issue_year": "Год выдачи",
        "therapist": "Терапевт",
        "ophthalmologist": "Окулист",
        "neurologist": "Невролог",
        "otolaryngologist": "ЛОР",
        "instrumental": "Инструментальные",
        "laboratory": "Лабораторные",
    }
)

_DRIVER_BACK_LABELS = {
    f"category_{side}_{key}": f"Категория {key.upper()} ({side_name})"
    for side, side_name in (("left", "лев"), ("right", "прав"))
    for key in _DRIVER_CATEGORY_KEYS
} | {
    f"restriction_{row}_{col}": f"Отметка {slot} ({side_name})"
    for slot, row in enumerate((14, 17, 20, 25, 27, 29, 31, 33), start=1)
    for col, side_name in ((29, "лев"), (62, "прав"))
} | _sided_field_labels({"chairman": "Председатель"})

_AMB_LABELS = {
    "blank_number": "Номер бланка",
    "visit_date": "Дата визита",
    "patient_name": "ФИО",
    "sex": "Пол",
    "birth_date": "Дата рождения",
    "subject": "Регион",
    "district": "Район",
    "city": "Город",
    "locality": "Населённый пункт",
    "street": "Улица",
    "phone": "Телефон",
    "residence_type": "Тип жительства",
    "oms_series": "ОМС серия",
    "oms_number": "ОМС номер",
    "snils": "СНИЛС",
    "document_type": "Документ вид",
    "document_series": "Документ серия",
    "document_number": "Документ номер",
    "workplace": "Место работы",
    "blood_group": "Группа крови",
    "rh_factor": "Резус-фактор",
    "allergies": "Аллергии",
} | {
    f"exam_{slot}_{key}": f"Осмотр {slot} {name}"
    for slot in range(1, 11)
    for key, name in (
        ("date", "дата"),
        ("title", "название"),
        ("complaints", "жалобы"),
        ("anamnesis", "анамнез"),
        ("objective", "объективно"),
        ("diagnosis", "диагноз"),
        ("doctor", "врач"),
    )
}

_PZ2_LABELS = {
    "blank_preliminary": "Бланк предварительный",
    "date_preliminary": "Дата предварительного",
    "blank_periodic": "Бланк периодический",
    "date_periodic": "Дата периодического",
    "issue_date": "Дата выдачи",
    "last_name": "Фамилия",
    "first_name": "Имя",
    "patronymic": "Отчество",
    "sex": "Пол",
    "birth_date": "Дата рождения",
    "address": "Адрес",
    "phone": "Телефон",
    "company": "Организация",
    "company_repeat": "Организация повтор",
    "department": "Подразделение",
    "position": "Должность",
    "harmfulness": "Вредности",
    "position_repeat": "Должность повтор",
    "harmfulness_repeat": "Вредности повтор",
    "signer": "Подписант",
} | {
    f"doctor_{slot}_{key}": f"Врач {slot} {name}"
    for slot in range(1, 11)
    for key, name in (
        ("sequence", "номер"),
        ("name", "ФИО"),
        ("date", "дата"),
        ("conclusion", "заключение"),
    )
}

_PROF2_LABELS = {
    "reference_date": "Дата справки",
    "patient_name": "ФИО",
    "birth_and_sex": "Дата рождения и пол",
    "address": "Адрес",
    "company": "Организация",
    "examination_date": "Дата освидетельствования",
    "position": "Должность",
    "harmfulness": "Вредности",
    "signature_date": "Дата подписи",
}

_PROF_CONCLUSION_29N_LABELS = {
    "blank_number": "Номер бланка",
    "narcologist": "Нарколог",
    "patient_name": "ФИО",
    "sex": "Пол",
    "birth_date": "Дата рождения",
    "workplace": "Место работы",
    "company": "Организация",
    "department": "Подразделение",
    "position": "Должность",
    "psychiatrist": "Психиатр",
    "harmfulness": "Вредности",
    "health_group": "Группа здоровья",
    "chairman": "Председатель",
    "position_repeat": "Должность повтор",
    "occupational_doctor": "Профпатолог",
    "issue_date": "Дата выдачи",
}

LEGACY_XLS_FIELD_LABELS: dict[str, dict[str, str]] = {
    "водительская лицевая.xls": _DRIVER_FRONT_LABELS,
    "водительская обратн ст.xls": _DRIVER_BACK_LABELS,
    "АМБ_карты_профосмотр_шаблон.xls": _AMB_LABELS,
    "Выписка из Амб карты (профа).xls": _PZ2_LABELS,
    "Справка_342н_псих_освид.xls": _PROF2_LABELS,
    "ПРОФОСМОТР 29Н.xls": _PROF_CONCLUSION_29N_LABELS,
}


def _placeholder_identity(index: int) -> str:
    return "".join(
        PLACEHOLDER_ONE if bit == "1" else PLACEHOLDER_ZERO
        for digit in f"{index:04X}"
        for bit in f"{int(digit, 16):04b}"
    )


def _old_placeholder_identity(index: int) -> str:
    return "".join(chr(0xFE00 + int(digit, 16)) for digit in f"{index:04X}")


def _hidden_marker(identity: str) -> str:
    return f"{PLACEHOLDER_START}{identity}{PLACEHOLDER_END}"


def _fixed_placeholder(marker: str) -> str:
    return marker + PLACEHOLDER_FILL * (PLACEHOLDER_LENGTH - len(marker))


def _old_fixed_placeholder(identity: str) -> str:
    marker = f"{OLD_PLACEHOLDER_START}{identity}{OLD_PLACEHOLDER_END}"
    return _fixed_placeholder(marker)


def _label_marker(label: str) -> str:
    """Build the readable «[Метка]» token the customer sees in the template."""
    marker = f"{PLACEHOLDER_LABEL_OPEN}{label}{PLACEHOLDER_LABEL_CLOSE}"
    if len(marker) > PLACEHOLDER_LENGTH:
        raise ValueError(f"Метка поля не помещается в маркер: {label}")
    return marker


def legacy_xls_label(spec: LegacyXlsTemplateSpec, field: LegacyXlsField) -> str:
    return LEGACY_XLS_FIELD_LABELS[spec.file_name][field.field_id]


def legacy_xls_placeholder(spec: LegacyXlsTemplateSpec, field: LegacyXlsField) -> str:
    # The visible label is padded with zero-width filler so every placeholder
    # keeps the same byte length and can be patched in place.
    return _fixed_placeholder(_label_marker(legacy_xls_label(spec, field)))


def hidden_legacy_xls_placeholder(spec: LegacyXlsTemplateSpec, field: LegacyXlsField) -> str:
    field_index = spec.fields.index(field) + 1
    return _fixed_placeholder(_hidden_marker(_placeholder_identity(field_index)))


def old_legacy_xls_placeholder(spec: LegacyXlsTemplateSpec, field: LegacyXlsField) -> str:
    field_index = spec.fields.index(field) + 1
    return _old_fixed_placeholder(_old_placeholder_identity(field_index))


def legacy_xls_markers(spec: LegacyXlsTemplateSpec, field: LegacyXlsField) -> tuple[str, ...]:
    # Templates edited before the readable labels shipped keep working.
    field_index = spec.fields.index(field) + 1
    return (
        _label_marker(legacy_xls_label(spec, field)),
        _hidden_marker(_placeholder_identity(field_index)),
        old_legacy_xls_placeholder(spec, field)[:6],
    )


def new_xls_label(spec: NewXlsTemplateSpec, coordinate: Cell) -> str:
    return NEW_XLS_FIELD_LABELS[spec.file_name][coordinate]


def new_xls_placeholder(spec: NewXlsTemplateSpec, coordinate: Cell) -> str:
    return _fixed_placeholder(_label_marker(new_xls_label(spec, coordinate)))


def hidden_new_xls_placeholder(spec: NewXlsTemplateSpec, coordinate: Cell) -> str:
    cell_index = spec.dynamic_cells.index(coordinate) + 1
    return _fixed_placeholder(_hidden_marker(_placeholder_identity(cell_index)))


def old_new_xls_placeholder(spec: NewXlsTemplateSpec, coordinate: Cell) -> str:
    cell_index = spec.dynamic_cells.index(coordinate) + 1
    return _old_fixed_placeholder(_old_placeholder_identity(cell_index))


def new_xls_marker(spec: NewXlsTemplateSpec, coordinate: Cell) -> str:
    return _label_marker(new_xls_label(spec, coordinate))


def new_xls_markers(spec: NewXlsTemplateSpec, coordinate: Cell) -> tuple[str, ...]:
    cell_index = spec.dynamic_cells.index(coordinate) + 1
    return (
        new_xls_marker(spec, coordinate),
        _hidden_marker(_placeholder_identity(cell_index)),
        old_new_xls_placeholder(spec, coordinate)[:6],
    )


def _check_placeholder_width(value: object, marker: str) -> None:
    """Reject a hand-typed label: patching relies on the fixed placeholder width."""
    if len(str(value or "")) != PLACEHOLDER_LENGTH:
        raise ValueError(
            f"Метка поля «{marker}» повреждена: её нельзя вводить вручную. "
            "Перенесите ячейку с меткой из исходного шаблона"
        )


def validate_editable_xls_template(path: Path, spec: NewXlsTemplateSpec) -> None:
    """Reject an edited XLS unless every movable field is still unambiguous."""
    try:
        book = xlrd.open_workbook(file_contents=path.read_bytes(), formatting_info=True)
    except Exception as exc:
        raise ValueError(f"Не удалось прочитать XLS: {exc}") from exc

    sheet_names = book.sheet_names()
    if sheet_names != [spec.sheet_name]:
        if spec.sheet_name not in sheet_names:
            raise ValueError(f"Обязательный печатный лист «{spec.sheet_name}» не найден или переименован")
        raise ValueError(
            f"Шаблон должен содержать только печатный лист «{spec.sheet_name}». "
            "Служебные листы загружать нельзя"
        )

    sheet = book.sheet_by_name(spec.sheet_name)
    locations: dict[Cell, list[Cell]] = {coordinate: [] for coordinate in spec.dynamic_cells}
    for row_index in range(sheet.nrows):
        for col_index in range(sheet.ncols):
            value = sheet.cell_value(row_index, col_index)
            if not isinstance(value, str):
                continue
            for coordinate in spec.dynamic_cells:
                markers = new_xls_markers(spec, coordinate)
                if any(marker in value for marker in markers):
                    locations[coordinate].append((row_index, col_index))

    for coordinate in spec.dynamic_cells:
        marker_locations = locations[coordinate]
        marker = new_xls_marker(spec, coordinate)
        if not marker_locations:
            raise ValueError(
                f"Удалена метка поля «{marker}». "
                "Верните исходный шаблон и повторите правку"
            )
        if len(marker_locations) != 1:
            raise ValueError(f"Метка поля «{marker}» продублирована")
        row_index, col_index = marker_locations[0]
        _check_placeholder_width(sheet.cell_value(row_index, col_index), marker)
        for row_low, row_high, col_low, col_high in sheet.merged_cells:
            if row_low <= row_index < row_high and col_low <= col_index < col_high:
                if (row_index, col_index) != (row_low, col_low):
                    raise ValueError(
                        f"Метка поля «{marker}» находится не в основной "
                        "ячейке объединённого диапазона"
                    )
                break


def legacy_xls_marker_locations(
    book,
    spec: LegacyXlsTemplateSpec,
) -> dict[str, tuple[str, int, int]]:
    locations: dict[str, list[tuple[str, int, int]]] = {field.field_id: [] for field in spec.fields}
    for sheet in book.sheets():
        for row_index in range(sheet.nrows):
            for col_index in range(sheet.ncols):
                value = sheet.cell_value(row_index, col_index)
                if not isinstance(value, str):
                    continue
                for field in spec.fields:
                    markers = legacy_xls_markers(spec, field)
                    if any(marker in value for marker in markers):
                        locations[field.field_id].append((sheet.name, row_index, col_index))

    result: dict[str, tuple[str, int, int]] = {}
    for field in spec.fields:
        marker_locations = locations[field.field_id]
        if not marker_locations:
            raise ValueError(f"Удалена метка поля «{_label_marker(legacy_xls_label(spec, field))}»")
        if len(marker_locations) != 1:
            raise ValueError(f"Метка поля «{_label_marker(legacy_xls_label(spec, field))}» продублирована")
        sheet_name, row_index, col_index = marker_locations[0]
        sheet = book.sheet_by_name(sheet_name)
        _check_placeholder_width(
            sheet.cell_value(row_index, col_index),
            _label_marker(legacy_xls_label(spec, field)),
        )
        for row_low, row_high, col_low, col_high in sheet.merged_cells:
            if row_low <= row_index < row_high and col_low <= col_index < col_high:
                if (row_index, col_index) != (row_low, col_low):
                    raise ValueError(
                        f"Метка поля «{_label_marker(legacy_xls_label(spec, field))}» находится не в основной "
                        "ячейке объединённого диапазона"
                    )
                break
        result[field.field_id] = (sheet_name, row_index, col_index)
    return result


def validate_legacy_editable_xls_template(path: Path, spec: LegacyXlsTemplateSpec) -> None:
    try:
        book = xlrd.open_workbook(file_contents=path.read_bytes(), formatting_info=True)
    except Exception as exc:
        raise ValueError(f"Не удалось прочитать XLS: {exc}") from exc
    if tuple(book.sheet_names()) != spec.sheet_names:
        raise ValueError(
            "Набор или порядок обязательных печатных листов изменён: "
            + ", ".join(spec.sheet_names)
        )
    legacy_xls_marker_locations(book, spec)


def strip_new_xls_placeholder_padding(value: object) -> str:
    return (
        str(value or "")
        .replace(OLD_PLACEHOLDER_START, "")
        .replace(OLD_PLACEHOLDER_END, "")
        .replace(PLACEHOLDER_FILL, "")
        .replace(PLACEHOLDER_ONE, "")
        .replace(PLACEHOLDER_JOIN, "")
        .replace("\x00", "")
        .strip()
    )


def _validate_field_labels() -> None:
    """Fail fast when a spec and its label table drift apart."""
    for spec in NEW_XLS_TEMPLATE_SPECS:
        labels = NEW_XLS_FIELD_LABELS.get(spec.file_name, {})
        if set(labels) != set(spec.dynamic_cells):
            raise RuntimeError(f"Метки полей не совпадают с ячейками {spec.file_name}")
        if len(set(labels.values())) != len(labels):
            raise RuntimeError(f"Метки полей повторяются в {spec.file_name}")
    for legacy_spec in LEGACY_XLS_TEMPLATE_SPECS:
        legacy_labels = LEGACY_XLS_FIELD_LABELS.get(legacy_spec.file_name, {})
        if set(legacy_labels) != {field.field_id for field in legacy_spec.fields}:
            raise RuntimeError(f"Метки полей не совпадают с полями {legacy_spec.file_name}")
        if len(set(legacy_labels.values())) != len(legacy_labels):
            raise RuntimeError(f"Метки полей повторяются в {legacy_spec.file_name}")


_validate_field_labels()
