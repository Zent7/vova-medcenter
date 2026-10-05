from pathlib import Path
import sys
import unittest
from unittest import mock

import xlrd


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import new_xls_templates  # noqa: E402
from app.services.new_xls_templates import (  # noqa: E402
    LEGACY_XLS_TEMPLATE_BY_FILE,
    NEW_XLS_TEMPLATE_BY_FILE,
    legacy_xls_marker_locations,
    validate_editable_xls_template,
)


TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates"


class XlsMarkerScanSpeedTests(unittest.TestCase):
    """Поиск меток шёл по клеткам листа и для каждой заново считал маркеры всех
    полей: выписка профа и амбулаторная карта печатались по 25–35 секунд. Маркеры
    должны считаться один раз на поле, а не на клетку."""

    def _count_marker_calls(self, spec, scan):
        with mock.patch.object(
            new_xls_templates, "legacy_xls_markers", wraps=new_xls_templates.legacy_xls_markers
        ) as legacy_calls, mock.patch.object(
            new_xls_templates, "new_xls_markers", wraps=new_xls_templates.new_xls_markers
        ) as new_calls:
            scan()
        return legacy_calls.call_count, new_calls.call_count

    def test_legacy_marker_search_computes_markers_once_per_field(self):
        for file_name in ("Выписка из Амб карты (профа).xls", "АМБ_карты_профосмотр_шаблон.xls"):
            with self.subTest(file_name):
                spec = LEGACY_XLS_TEMPLATE_BY_FILE[file_name.casefold()]
                book = xlrd.open_workbook(str(TEMPLATES_DIR / file_name), formatting_info=True)

                legacy_calls, _ = self._count_marker_calls(
                    spec, lambda: legacy_xls_marker_locations(book, spec)
                )

                self.assertEqual(legacy_calls, len(spec.fields))

    def test_new_template_validation_computes_markers_once_per_field(self):
        spec = next(
            spec
            for spec in NEW_XLS_TEMPLATE_BY_FILE.values()
            if (TEMPLATES_DIR / spec.file_name).is_file()
        )
        path = TEMPLATES_DIR / spec.file_name

        _, new_calls = self._count_marker_calls(spec, lambda: validate_editable_xls_template(path, spec))

        self.assertEqual(new_calls, len(spec.dynamic_cells))


if __name__ == "__main__":
    unittest.main()
