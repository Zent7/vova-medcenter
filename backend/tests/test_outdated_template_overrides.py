"""Клиентская версия бланка не должна прятать новые поля шаблона.

Загруженный заказчиком файл лежит в хранилище и перекрывает встроенный, а
деплой хранилище не трогает. Для бланков из списка и для Excel-бланков со
свободным макетом приложение само откладывает версию, в которой нет метки
нового поля.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

import xlrd
from xlutils.copy import copy as copy_xls_workbook


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import template_catalog  # noqa: E402
from app.services.new_xls_templates import NEW_XLS_TEMPLATE_BY_FILE  # noqa: E402


TEMPLATE_FILE_NAME = "095У_справка_шаблон.docx"
REQUIRED_TOKEN = "[Certificate095EducationInstitution]"
BUNDLED_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "templates"
    / "Templates"
    / TEMPLATE_FILE_NAME
)


def write_docx(path: Path, body: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "word/document.xml",
            f"<w:document xmlns:w=\"w\"><w:body>{body}</w:body></w:document>",
        )


class OutdatedTemplateOverrideTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.overrides_root = Path(self.temporary_directory.name)
        self.override_path = self.overrides_root / TEMPLATE_FILE_NAME
        patcher = mock.patch.object(
            template_catalog,
            "get_template_override_path",
            lambda file_name: self.overrides_root / file_name,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def retired_files(self) -> list[Path]:
        return sorted(self.overrides_root.glob(f"{TEMPLATE_FILE_NAME}.retired-*"))

    def test_bundled_095_carries_the_token_the_cleanup_looks_for(self):
        self.assertTrue(template_catalog.docx_text_contains(BUNDLED_TEMPLATE_PATH, REQUIRED_TOKEN))

    def test_override_without_the_new_field_is_retired(self):
        write_docx(self.override_path, "<w:t>Диагноз заболевания</w:t>")

        template_catalog.retire_outdated_template_overrides()

        self.assertFalse(self.override_path.exists())
        self.assertEqual(len(self.retired_files()), 1)

    def test_override_that_already_has_the_field_is_kept(self):
        write_docx(self.override_path, f"<w:t>{REQUIRED_TOKEN}</w:t>")

        template_catalog.retire_outdated_template_overrides()

        self.assertTrue(self.override_path.is_file())
        self.assertEqual(self.retired_files(), [])

    def test_token_split_by_word_across_runs_is_still_found(self):
        write_docx(
            self.override_path,
            "<w:t>[Certificate095</w:t><w:t>EducationInstitution]</w:t>",
        )

        template_catalog.retire_outdated_template_overrides()

        self.assertTrue(self.override_path.is_file())

    def test_a_damaged_override_is_left_alone(self):
        self.override_path.write_bytes(b"not a docx")

        template_catalog.retire_outdated_template_overrides()

        self.assertTrue(self.override_path.is_file())
        self.assertEqual(self.retired_files(), [])

    def test_nothing_happens_without_an_override(self):
        template_catalog.retire_outdated_template_overrides()

        self.assertEqual(list(self.overrides_root.iterdir()), [])

    def test_override_is_dropped_only_when_a_bundled_template_exists(self):
        write_docx(self.override_path, "<w:t>старый бланк</w:t>")
        with mock.patch.object(
            template_catalog,
            "get_templates_root",
            lambda: Path(self.temporary_directory.name) / "нет-такой-папки",
        ):
            template_catalog.retire_outdated_template_overrides()

        self.assertTrue(self.override_path.is_file())

    def test_a_real_previous_095_override_is_retired(self):
        """Старый встроенный бланк 095у — ровно то, что сейчас лежит на сайте."""
        previous_template = self.overrides_root / TEMPLATE_FILE_NAME
        shutil.copy2(BUNDLED_TEMPLATE_PATH, previous_template)
        with zipfile.ZipFile(previous_template) as archive:
            payload = {name: archive.read(name) for name in archive.namelist()}
        document = payload["word/document.xml"].decode("utf-8").replace(REQUIRED_TOKEN, "")
        payload["word/document.xml"] = document.encode("utf-8")
        with zipfile.ZipFile(previous_template, "w") as archive:
            for name, data in payload.items():
                archive.writestr(name, data)

        template_catalog.retire_outdated_template_overrides()

        self.assertFalse(previous_template.exists())
        self.assertEqual(len(self.retired_files()), 1)


TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates"
TRACTOR_FRONT_FILE_NAME = "трактор лиц ст.xls"
TRACTOR_FRONT_RESULT_CELLS = ((39, 12), (39, 39), (41, 12), (41, 39))
DRIVER_FRONT_FILE_NAME = "водительская лицевая.xls"


class OutdatedXlsTemplateOverrideTests(unittest.TestCase):
    """Excel-бланк без метки нового поля печать заполнить не может.

    Раньше печать 071у молча брала встроенный шаблон, и в услуге выходил не
    тот бланк, что лежал на странице «Шаблоны». Теперь такую версию
    откладывают при старте, и оба места берут один и тот же файл.
    """

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.overrides_root = Path(self.temporary_directory.name)
        patcher = mock.patch.object(
            template_catalog,
            "get_template_override_path",
            lambda file_name: self.overrides_root / file_name,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def retired_files(self, file_name: str) -> list[Path]:
        return sorted(self.overrides_root.glob(f"{file_name}.retired-*"))

    def write_tractor_front_without_result_markers(self) -> Path:
        """Копия 071у, сохранённая до того, как на лицевую добавили две строки результатов."""
        source_book = xlrd.open_workbook(str(TEMPLATES_DIR / TRACTOR_FRONT_FILE_NAME), formatting_info=True)
        outdated_book = copy_xls_workbook(source_book)
        for coordinate in TRACTOR_FRONT_RESULT_CELLS:
            outdated_book.get_sheet(0).write(*coordinate, "")
        override_path = self.overrides_root / TRACTOR_FRONT_FILE_NAME
        outdated_book.save(str(override_path))
        return override_path

    def test_tractor_front_without_the_result_rows_is_retired(self):
        override_path = self.write_tractor_front_without_result_markers()

        template_catalog.retire_outdated_template_overrides()

        self.assertFalse(override_path.exists())
        self.assertEqual(len(self.retired_files(TRACTOR_FRONT_FILE_NAME)), 1)

    def test_after_retiring_download_and_print_resolve_the_same_bundled_file(self):
        self.write_tractor_front_without_result_markers()
        # Путь в базе мог остаться на клиентской версии со времён загрузки.
        template = mock.Mock(
            file_name=TRACTOR_FRONT_FILE_NAME,
            file_path=str(self.overrides_root / TRACTOR_FRONT_FILE_NAME),
        )

        template_catalog.retire_outdated_template_overrides()

        self.assertEqual(
            template_catalog.resolve_template_file(template),
            (TEMPLATES_DIR / TRACTOR_FRONT_FILE_NAME).resolve(),
        )

    def test_current_copies_of_free_layout_templates_are_kept(self):
        for file_name in (TRACTOR_FRONT_FILE_NAME, DRIVER_FRONT_FILE_NAME, "трактор об ст.xls"):
            with self.subTest(file_name=file_name):
                override_path = self.overrides_root / file_name
                shutil.copy2(TEMPLATES_DIR / file_name, override_path)

                template_catalog.retire_outdated_template_overrides()

                self.assertTrue(override_path.is_file())
                self.assertEqual(self.retired_files(file_name), [])

    def test_a_moved_field_is_not_mistaken_for_a_missing_one(self):
        spec = NEW_XLS_TEMPLATE_BY_FILE[TRACTOR_FRONT_FILE_NAME.casefold()]
        source_book = xlrd.open_workbook(str(TEMPLATES_DIR / TRACTOR_FRONT_FILE_NAME), formatting_info=True)
        source_sheet = source_book.sheet_by_name(spec.sheet_name)
        edited_book = copy_xls_workbook(source_book)
        edited_sheet = edited_book.get_sheet(0)
        coordinate = (39, 12)
        edited_sheet.write(0, 0, source_sheet.cell_value(*coordinate))
        edited_sheet.write(*coordinate, "")
        override_path = self.overrides_root / TRACTOR_FRONT_FILE_NAME
        edited_book.save(str(override_path))

        template_catalog.retire_outdated_template_overrides()

        self.assertTrue(override_path.is_file())

    def test_an_unreadable_xls_override_is_left_alone(self):
        override_path = self.overrides_root / DRIVER_FRONT_FILE_NAME
        override_path.write_bytes(b"not an xls")

        template_catalog.retire_outdated_template_overrides()

        self.assertTrue(override_path.is_file())
        self.assertEqual(self.retired_files(DRIVER_FRONT_FILE_NAME), [])


if __name__ == "__main__":
    unittest.main()
