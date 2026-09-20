"""Клиентская версия бланка не должна прятать новые поля шаблона.

Загруженный заказчиком файл лежит в хранилище и перекрывает встроенный, а
деплой хранилище не трогает. Для бланков из списка приложение само откладывает
версию, в которой нет метки нового поля.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import template_catalog  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
