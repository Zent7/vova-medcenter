from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import xlrd


Cell = tuple[int, int]
PLACEHOLDER_LENGTH = 240
PLACEHOLDER_START = "\u2060"
PLACEHOLDER_END = "\u2063"
PLACEHOLDER_FILL = "\u200b"


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


def new_xls_placeholder(spec: NewXlsTemplateSpec, coordinate: Cell) -> str:
    cell_index = spec.dynamic_cells.index(coordinate) + 1
    identity = "".join(chr(0xFE00 + int(digit, 16)) for digit in f"{cell_index:04X}")
    marker = f"{PLACEHOLDER_START}{identity}{PLACEHOLDER_END}"
    return marker + PLACEHOLDER_FILL * (PLACEHOLDER_LENGTH - len(marker))


def new_xls_marker(spec: NewXlsTemplateSpec, coordinate: Cell) -> str:
    return new_xls_placeholder(spec, coordinate)[:6]


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
    locations: dict[str, list[Cell]] = {
        new_xls_marker(spec, coordinate): [] for coordinate in spec.dynamic_cells
    }
    for row_index in range(sheet.nrows):
        for col_index in range(sheet.ncols):
            value = sheet.cell_value(row_index, col_index)
            if not isinstance(value, str):
                continue
            for marker in locations:
                if marker in value:
                    locations[marker].append((row_index, col_index))

    for coordinate in spec.dynamic_cells:
        marker = new_xls_marker(spec, coordinate)
        marker_locations = locations[marker]
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


def strip_new_xls_placeholder_padding(value: object) -> str:
    return (
        str(value or "")
        .replace(PLACEHOLDER_START, "")
        .replace(PLACEHOLDER_END, "")
        .replace(PLACEHOLDER_FILL, "")
        .replace("\x00", "")
        .strip()
    )
