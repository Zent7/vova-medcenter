"""Начальный набор бланков центра: Centers/<код центра>/ в репозитории.

Заказчик переоформил бланки под каждый центр. Набор лежит в репозитории и при
старте раскладывается по папке центра ``center-<id>`` хранилища правок, где его
подхватывает печать и страница «Шаблоны». Раскладка однократная: своя копия
центра и удалённый файл не затираются и не оживают.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
import zipfile

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


os.environ.setdefault("ALLOW_SQLITE", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.documents import list_document_templates, reset_document_template  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.document_template import DocumentTemplate  # noqa: E402
from app.services import template_catalog  # noqa: E402
from app.services.seed import WORKSPACE_CENTERS  # noqa: E402
from app.services.template_catalog import (  # noqa: E402
    CENTER_DEFAULTS_FOLDER,
    CENTER_DEFAULTS_MARKER,
    SUPPORTED_TEMPLATE_EXTENSIONS,
    TEMPLATE_DISPLAY_NAMES,
    _override_is_outdated,
    get_template_override_path,
    resolve_template_file,
    restore_center_template_default,
    retire_outdated_template_overrides,
    seed_center_template_defaults,
)


ASSETS_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "assets" / "templates"
BUNDLED_DIR = ASSETS_TEMPLATES_DIR / "Templates"
DEFAULTS_DIR = ASSETS_TEMPLATES_DIR / CENTER_DEFAULTS_FOLDER
DOCX_FILE_NAME = "082у_шаблон.docx"
OTHER_FILE_NAME = "ГТО_шаблон.docx"
CENTER_CODE = "center-x"


class SeededStorageTestCase(unittest.TestCase):
    """Хранилище правок и корень шаблонов во временной папке."""

    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        base = Path(temporary_directory.name)
        self.storage_root = base / "template-overrides"
        self.storage_root.mkdir()
        self.defaults_root = base / CENTER_DEFAULTS_FOLDER / CENTER_CODE
        self.defaults_root.mkdir(parents=True)
        original_dir = settings.document_template_overrides_dir
        settings.document_template_overrides_dir = str(self.storage_root)
        self.addCleanup(setattr, settings, "document_template_overrides_dir", original_dir)
        patcher = mock.patch.object(template_catalog, "get_templates_root", return_value=base / "Templates")
        patcher.start()
        self.addCleanup(patcher.stop)

    def center_dir(self, center_id: int) -> Path:
        return self.storage_root.resolve() / f"center-{center_id}"

    def write_default(self, file_name: str, content: bytes) -> Path:
        path = self.defaults_root / file_name
        path.write_bytes(content)
        return path


class SeedCenterTemplateDefaultsTests(SeededStorageTestCase):
    def test_the_set_lands_in_the_folder_of_its_center_only(self):
        self.write_default(DOCX_FILE_NAME, b"set")

        placed = seed_center_template_defaults([(7, CENTER_CODE), (8, "center-without-set")])

        self.assertEqual(placed, [f"7/{DOCX_FILE_NAME}"])
        self.assertEqual((self.center_dir(7) / DOCX_FILE_NAME).read_bytes(), b"set")
        self.assertFalse(self.center_dir(8).exists())

    def test_files_of_unsupported_types_are_not_placed(self):
        self.write_default("notes.txt", b"not a template")

        self.assertEqual(seed_center_template_defaults([(7, CENTER_CODE)]), [])
        self.assertFalse((self.center_dir(7) / "notes.txt").exists())

    def test_a_copy_the_center_already_has_stays_untouched_for_good(self):
        self.write_default(DOCX_FILE_NAME, b"set")
        own_copy = get_template_override_path(DOCX_FILE_NAME, 7)
        own_copy.parent.mkdir(parents=True)
        own_copy.write_bytes(b"customer copy")

        seed_center_template_defaults([(7, CENTER_CODE)])
        own_copy.unlink()
        seed_center_template_defaults([(7, CENTER_CODE)])

        self.assertFalse(own_copy.exists())

    def backup_shared_copy(self, content: bytes, name: str = DOCX_FILE_NAME) -> None:
        backup_dir = self.storage_root / template_catalog.SHARED_OVERRIDES_BACKUP_FOLDER
        backup_dir.mkdir(exist_ok=True)
        (backup_dir / name).write_bytes(content)

    def test_a_copy_left_over_from_the_split_is_replaced_by_the_set(self):
        # При разделении общих версий центр получил чужую копию; своей правки у него нет.
        self.write_default(DOCX_FILE_NAME, b"set")
        self.backup_shared_copy(b"shared copy")
        own_copy = get_template_override_path(DOCX_FILE_NAME, 7)
        own_copy.parent.mkdir(parents=True)
        own_copy.write_bytes(b"shared copy")

        placed = seed_center_template_defaults([(7, CENTER_CODE)])

        self.assertEqual(placed, [f"7/{DOCX_FILE_NAME}"])
        self.assertEqual(own_copy.read_bytes(), b"set")
        # Дальше это обычная разложенная копия: правка центра её больше не заменяет.
        own_copy.write_bytes(b"customer edit")
        self.assertEqual(seed_center_template_defaults([(7, CENTER_CODE)]), [])
        self.assertEqual(own_copy.read_bytes(), b"customer edit")

    def test_a_copy_left_over_from_the_split_is_found_among_stamped_backups(self):
        self.write_default(DOCX_FILE_NAME, b"set")
        self.backup_shared_copy(b"shared copy", f"{DOCX_FILE_NAME}.20261005190000")
        own_copy = get_template_override_path(DOCX_FILE_NAME, 7)
        own_copy.parent.mkdir(parents=True)
        own_copy.write_bytes(b"shared copy")

        seed_center_template_defaults([(7, CENTER_CODE)])

        self.assertEqual(own_copy.read_bytes(), b"set")

    def test_a_copy_the_center_changed_after_the_split_stays(self):
        self.write_default(DOCX_FILE_NAME, b"set")
        self.backup_shared_copy(b"shared copy")
        own_copy = get_template_override_path(DOCX_FILE_NAME, 7)
        own_copy.parent.mkdir(parents=True)
        own_copy.write_bytes(b"uploaded by the center")

        self.assertEqual(seed_center_template_defaults([(7, CENTER_CODE)]), [])
        self.assertEqual(own_copy.read_bytes(), b"uploaded by the center")

    def test_a_split_copy_of_another_file_is_not_mistaken_for_this_one(self):
        self.write_default(DOCX_FILE_NAME, b"set")
        self.backup_shared_copy(b"shared copy", OTHER_FILE_NAME)
        own_copy = get_template_override_path(DOCX_FILE_NAME, 7)
        own_copy.parent.mkdir(parents=True)
        own_copy.write_bytes(b"shared copy")

        self.assertEqual(seed_center_template_defaults([(7, CENTER_CODE)]), [])
        self.assertEqual(own_copy.read_bytes(), b"shared copy")

    def test_a_removed_file_does_not_come_back_on_restart(self):
        self.write_default(DOCX_FILE_NAME, b"set")
        seed_center_template_defaults([(7, CENTER_CODE)])
        (self.center_dir(7) / DOCX_FILE_NAME).unlink()

        self.assertEqual(seed_center_template_defaults([(7, CENTER_CODE)]), [])
        self.assertFalse((self.center_dir(7) / DOCX_FILE_NAME).exists())

    def test_a_second_start_changes_nothing(self):
        self.write_default(DOCX_FILE_NAME, b"set")
        seed_center_template_defaults([(7, CENTER_CODE)])
        marker = self.center_dir(7) / CENTER_DEFAULTS_MARKER
        marker_bytes = marker.read_bytes()

        self.assertEqual(seed_center_template_defaults([(7, CENTER_CODE)]), [])
        self.assertEqual(marker.read_bytes(), marker_bytes)

    def test_a_new_version_of_the_set_replaces_a_copy_the_customer_did_not_touch(self):
        default = self.write_default(DOCX_FILE_NAME, b"first version")
        seed_center_template_defaults([(7, CENTER_CODE)])
        default.write_bytes(b"second version")

        placed = seed_center_template_defaults([(7, CENTER_CODE)])

        self.assertEqual(placed, [f"7/{DOCX_FILE_NAME}"])
        self.assertEqual((self.center_dir(7) / DOCX_FILE_NAME).read_bytes(), b"second version")

    def test_a_new_version_of_the_set_does_not_overwrite_the_customers_edit(self):
        default = self.write_default(DOCX_FILE_NAME, b"first version")
        seed_center_template_defaults([(7, CENTER_CODE)])
        (self.center_dir(7) / DOCX_FILE_NAME).write_bytes(b"customer edit")
        default.write_bytes(b"second version")

        self.assertEqual(seed_center_template_defaults([(7, CENTER_CODE)]), [])
        self.assertEqual((self.center_dir(7) / DOCX_FILE_NAME).read_bytes(), b"customer edit")

    def test_a_center_code_that_climbs_out_of_the_folder_is_ignored(self):
        self.write_default(DOCX_FILE_NAME, b"set")

        self.assertEqual(seed_center_template_defaults([(7, f"../{CENTER_CODE}")]), [])
        self.assertFalse(self.center_dir(7).exists())

    def test_a_broken_marker_does_not_stop_the_start(self):
        self.write_default(DOCX_FILE_NAME, b"set")
        self.center_dir(7).mkdir()
        (self.center_dir(7) / CENTER_DEFAULTS_MARKER).write_text("{not json", encoding="utf-8")

        seed_center_template_defaults([(7, CENTER_CODE)])

        self.assertEqual((self.center_dir(7) / DOCX_FILE_NAME).read_bytes(), b"set")


class RestoreCenterTemplateDefaultTests(SeededStorageTestCase):
    def test_restore_puts_the_set_back_over_a_customer_edit(self):
        self.write_default(DOCX_FILE_NAME, b"set")
        seed_center_template_defaults([(7, CENTER_CODE)])
        (self.center_dir(7) / DOCX_FILE_NAME).write_bytes(b"customer edit")

        self.assertTrue(restore_center_template_default(7, CENTER_CODE, DOCX_FILE_NAME))

        self.assertEqual((self.center_dir(7) / DOCX_FILE_NAME).read_bytes(), b"set")

    def test_restore_brings_back_a_removed_file(self):
        self.write_default(DOCX_FILE_NAME, b"set")

        self.assertTrue(restore_center_template_default(7, CENTER_CODE, DOCX_FILE_NAME))

        self.assertEqual((self.center_dir(7) / DOCX_FILE_NAME).read_bytes(), b"set")

    def test_restore_does_nothing_for_a_file_outside_the_set(self):
        self.write_default(DOCX_FILE_NAME, b"set")

        self.assertFalse(restore_center_template_default(7, CENTER_CODE, OTHER_FILE_NAME))
        self.assertFalse((self.center_dir(7) / OTHER_FILE_NAME).exists())

    def test_a_restored_copy_is_refreshed_by_a_new_version_of_the_set(self):
        default = self.write_default(DOCX_FILE_NAME, b"first version")
        restore_center_template_default(7, CENTER_CODE, DOCX_FILE_NAME)
        default.write_bytes(b"second version")

        seed_center_template_defaults([(7, CENTER_CODE)])

        self.assertEqual((self.center_dir(7) / DOCX_FILE_NAME).read_bytes(), b"second version")


class ResetRouteRestoresTheSetTests(unittest.TestCase):
    """«Вернуть исходный» у центра с набором возвращает его набор, а не общий бланк."""

    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.storage_root = Path(temporary_directory.name) / "template-overrides"
        self.storage_root.mkdir()
        original_dir = settings.document_template_overrides_dir
        settings.document_template_overrides_dir = str(self.storage_root)
        self.addCleanup(setattr, settings, "document_template_overrides_dir", original_dir)

        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        with Session(self.engine) as db:
            with_set = Center(code="center-c", name="Со своим набором")
            without_set = Center(code="center-without-set", name="Без набора")
            db.add_all([with_set, without_set])
            db.add(
                DocumentTemplate(
                    code="route-082",
                    name="082у",
                    file_name=DOCX_FILE_NAME,
                    file_path=str(BUNDLED_DIR / DOCX_FILE_NAME),
                    template_type="docx",
                    output_format="docx",
                    is_active=True,
                )
            )
            db.commit()
            self.with_set_id = with_set.id
            self.without_set_id = without_set.id
            self.template_id = db.query(DocumentTemplate).one().id

    def admin(self) -> SimpleNamespace:
        return SimpleNamespace(pinned_center_id=None, sees_all_centers=True, work_centers=[])

    def test_reset_returns_the_center_set(self):
        shipped = (DEFAULTS_DIR / "center-c" / DOCX_FILE_NAME).read_bytes()
        override = get_template_override_path(DOCX_FILE_NAME, self.with_set_id)
        override.parent.mkdir(parents=True)
        override.write_bytes(b"customer edit")

        with Session(self.engine) as db:
            response = reset_document_template(self.template_id, self.with_set_id, self.admin(), db)

        self.assertEqual(override.read_bytes(), shipped)
        self.assertTrue(response.has_override)

    def test_reset_of_a_center_without_a_set_drops_its_copy(self):
        override = get_template_override_path(DOCX_FILE_NAME, self.without_set_id)
        override.parent.mkdir(parents=True)
        override.write_bytes(b"customer edit")

        with Session(self.engine) as db:
            response = reset_document_template(self.template_id, self.without_set_id, self.admin(), db)
            template = db.get(DocumentTemplate, self.template_id)
            resolved = resolve_template_file(template, self.without_set_id)

        self.assertFalse(override.exists())
        self.assertFalse(response.has_override)
        self.assertEqual(resolved, (BUNDLED_DIR / DOCX_FILE_NAME).resolve())

    def test_the_listing_marks_the_seeded_copy_as_the_centers_own(self):
        seed_center_template_defaults([(self.with_set_id, "center-c")])

        with Session(self.engine) as db:
            listed = list_document_templates(self.with_set_id, db)
            other = list_document_templates(self.without_set_id, db)

        self.assertTrue(listed[0].has_override)
        self.assertFalse(other[0].has_override)


def center_default_files() -> list[Path]:
    return sorted(
        path
        for center_dir in DEFAULTS_DIR.iterdir()
        if center_dir.is_dir()
        for path in center_dir.iterdir()
        if path.is_file()
    )


class ShippedCenterSetsTests(unittest.TestCase):
    """Файлы, которые лежат в репозитории, должны годиться к печати."""

    def test_every_set_folder_belongs_to_a_known_center(self):
        known_codes = {code for code, _ in WORKSPACE_CENTERS}
        folders = {path.name for path in DEFAULTS_DIR.iterdir() if path.is_dir()}

        self.assertTrue(folders)
        self.assertLessEqual(folders, known_codes)

    def test_every_file_is_a_catalog_template_of_its_own_type(self):
        for path in center_default_files():
            with self.subTest(path=f"{path.parent.name}/{path.name}"):
                self.assertIn(path.suffix.lower(), SUPPORTED_TEMPLATE_EXTENSIONS)
                # Имя должно совпасть с каталогом до буквы: латинская «C» вместо
                # русской «С» даёт файл, который никто не подхватит.
                self.assertIn(path.name, TEMPLATE_DISPLAY_NAMES)
                bundled = BUNDLED_DIR / path.name
                self.assertTrue(bundled.is_file())

    def test_every_file_passes_the_checks_of_the_current_field_markers(self):
        for path in center_default_files():
            with self.subTest(path=f"{path.parent.name}/{path.name}"):
                self.assertFalse(_override_is_outdated(path.name, path))

    def test_the_start_keeps_the_whole_set_in_place(self):
        # Набор раскладывается до проверки на устаревшие метки; если бы файл её
        # не проходил, при старте он уехал бы в «.retired-…» и центр печатал бы
        # общий бланк.
        for center_dir in DEFAULTS_DIR.iterdir():
            if not center_dir.is_dir():
                continue
            with self.subTest(center=center_dir.name), tempfile.TemporaryDirectory() as storage:
                original_dir = settings.document_template_overrides_dir
                settings.document_template_overrides_dir = storage
                try:
                    seed_center_template_defaults([(5, center_dir.name)])
                    retire_outdated_template_overrides()
                    placed = sorted(path.name for path in (Path(storage) / "center-5").iterdir() if path.is_file())
                finally:
                    settings.document_template_overrides_dir = original_dir
                shipped = sorted(path.name for path in center_dir.iterdir() if path.is_file())
                self.assertEqual(placed, sorted([*shipped, CENTER_DEFAULTS_MARKER]))


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        parts = [
            re.sub(r"<[^>]+>", "", archive.read(name).decode("utf-8"))
            for name in archive.namelist()
            if re.fullmatch(r"word/(document|header\d*|footer\d*)\.xml", name)
        ]
    return "\n".join(parts)


class FirstHealthResortSetTests(unittest.TestCase):
    """Набор ПЕРВОЙ ЗДРАВНИЦЫ (center-c) не должен нести реквизиты других центров."""

    OTHER_CENTERS = re.compile(r"мед-?\s?авто|медил[эе]нд|заневск|мурино", re.IGNORECASE)

    def test_word_forms_carry_this_center_and_not_the_others(self):
        word_files = sorted((DEFAULTS_DIR / "center-c").glob("*.docx"))
        self.assertTrue(word_files)
        for path in word_files:
            with self.subTest(path=path.name):
                text = docx_text(path)
                self.assertIn("ПЕРВАЯ ЗДРАВНИЦА", text)
                self.assertIsNone(self.OTHER_CENTERS.search(text))


if __name__ == "__main__":
    unittest.main()
