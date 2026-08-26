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
    LegacyXlsTemplateSpec("ВУ.xls", ("Водительская Лицевая", "Водительская Оборотная"), _DRIVER_FRONT_FIELDS + _DRIVER_BACK_FIELDS),
    LegacyXlsTemplateSpec("АМБ_карты_профосмотр_шаблон.xls", ("Амб",), _AMB_HEADER_FIELDS + _AMB_BLOCK_FIELDS),
    LegacyXlsTemplateSpec("Выписка из Амб карты (профа).xls", ("ПЗ2",), _PZ2_HEADER_FIELDS + _PZ2_DOCTOR_FIELDS),
    LegacyXlsTemplateSpec("Справка_342н_псих_освид.xls", ("Проф2",), _PROF2_FIELDS),
    LegacyXlsTemplateSpec("ПРОФОСМОТР 29Н.xls", ("ПРОФОСМОТР",), _PROF_CONCLUSION_29N_FIELDS),
)
LEGACY_XLS_TEMPLATE_BY_FILE = {spec.file_name.casefold(): spec for spec in LEGACY_XLS_TEMPLATE_SPECS}


def _placeholder_identity(index: int) -> str:
    return "".join(
        PLACEHOLDER_ONE if bit == "1" else PLACEHOLDER_ZERO
        for digit in f"{index:04X}"
        for bit in f"{int(digit, 16):04b}"
    )


def _old_placeholder_identity(index: int) -> str:
    return "".join(chr(0xFE00 + int(digit, 16)) for digit in f"{index:04X}")


def _fixed_placeholder(identity: str) -> str:
    marker = f"{PLACEHOLDER_START}{identity}{PLACEHOLDER_END}"
    return marker + PLACEHOLDER_FILL * (PLACEHOLDER_LENGTH - len(marker))


def _old_fixed_placeholder(identity: str) -> str:
    marker = f"{OLD_PLACEHOLDER_START}{identity}{OLD_PLACEHOLDER_END}"
    return marker + PLACEHOLDER_FILL * (PLACEHOLDER_LENGTH - len(marker))


def legacy_xls_placeholder(spec: LegacyXlsTemplateSpec, field: LegacyXlsField) -> str:
    field_index = spec.fields.index(field) + 1
    return _fixed_placeholder(_placeholder_identity(field_index))


def old_legacy_xls_placeholder(spec: LegacyXlsTemplateSpec, field: LegacyXlsField) -> str:
    field_index = spec.fields.index(field) + 1
    return _old_fixed_placeholder(_old_placeholder_identity(field_index))


def legacy_xls_markers(spec: LegacyXlsTemplateSpec, field: LegacyXlsField) -> tuple[str, ...]:
    return (
        legacy_xls_placeholder(spec, field)[: len(PLACEHOLDER_START) + 16 + len(PLACEHOLDER_END)],
        old_legacy_xls_placeholder(spec, field)[:6],
    )


def new_xls_placeholder(spec: NewXlsTemplateSpec, coordinate: Cell) -> str:
    cell_index = spec.dynamic_cells.index(coordinate) + 1
    return _fixed_placeholder(_placeholder_identity(cell_index))


def old_new_xls_placeholder(spec: NewXlsTemplateSpec, coordinate: Cell) -> str:
    cell_index = spec.dynamic_cells.index(coordinate) + 1
    return _old_fixed_placeholder(_old_placeholder_identity(cell_index))


def new_xls_marker(spec: NewXlsTemplateSpec, coordinate: Cell) -> str:
    return new_xls_placeholder(spec, coordinate)[: len(PLACEHOLDER_START) + 16 + len(PLACEHOLDER_END)]


def new_xls_markers(spec: NewXlsTemplateSpec, coordinate: Cell) -> tuple[str, ...]:
    return (new_xls_marker(spec, coordinate), old_new_xls_placeholder(spec, coordinate)[:6])


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
        if not marker_locations:
            raise ValueError(
                f"Удалён скрытый маркер поля {spec.dynamic_cells.index(coordinate) + 1}. "
                "Верните исходный шаблон и повторите правку"
            )
        if len(marker_locations) != 1:
            raise ValueError(
                f"Скрытый маркер поля {spec.dynamic_cells.index(coordinate) + 1} продублирован"
            )
        row_index, col_index = marker_locations[0]
        for row_low, row_high, col_low, col_high in sheet.merged_cells:
            if row_low <= row_index < row_high and col_low <= col_index < col_high:
                if (row_index, col_index) != (row_low, col_low):
                    raise ValueError(
                        f"Маркер поля {spec.dynamic_cells.index(coordinate) + 1} находится не в основной "
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
            raise ValueError(f"Удалён скрытый маркер поля «{field.field_id}»")
        if len(marker_locations) != 1:
            raise ValueError(f"Скрытый маркер поля «{field.field_id}» продублирован")
        sheet_name, row_index, col_index = marker_locations[0]
        sheet = book.sheet_by_name(sheet_name)
        for row_low, row_high, col_low, col_high in sheet.merged_cells:
            if row_low <= row_index < row_high and col_low <= col_index < col_high:
                if (row_index, col_index) != (row_low, col_low):
                    raise ValueError(
                        f"Маркер поля «{field.field_id}» находится не в основной ячейке объединённого диапазона"
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
