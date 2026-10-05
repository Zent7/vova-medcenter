"""У каждого медцентра свои клиентские версии бланков.

Файл, который заказчик загружает на странице «Шаблоны», лежит в папке центра
``center-<id>`` хранилища правок и виден только этому центру: другой центр
печатает свою копию или встроенный бланк. Встроенные шаблоны общие.
"""

from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
import zipfile

from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


os.environ.setdefault("ALLOW_SQLITE", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.documents import (  # noqa: E402
    list_document_templates,
    open_document_template,
    replace_document_template,
    reset_document_template,
)
from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.document_template import DocumentTemplate  # noqa: E402
from app.services import template_catalog  # noqa: E402
from app.services.template_catalog import (  # noqa: E402
    SHARED_OVERRIDES_BACKUP_FOLDER,
    center_ids_with_override_folders,
    get_template_override_path,
    resolve_template_file,
    retire_outdated_template_overrides,
    split_shared_template_overrides,
    template_has_override,
)


TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "assets" / "templates" / "Templates"
DOCX_FILE_NAME = "082у_шаблон.docx"
GTO_FILE_NAME = "ГТО_шаблон.docx"


def write_docx(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "word/document.xml",
            f"<w:document xmlns:w=\"w\"><w:body>{body}</w:body></w:document>",
        )


class OverridesStorageTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.storage_root = Path(self.temporary_directory.name) / "template-overrides"
        self.storage_root.mkdir()
        original_overrides_dir = settings.document_template_overrides_dir
        settings.document_template_overrides_dir = str(self.storage_root)
        self.addCleanup(setattr, settings, "document_template_overrides_dir", original_overrides_dir)

    def center_dir(self, center_id: int) -> Path:
        return self.storage_root.resolve() / f"center-{center_id}"


class CenterOverridePathTests(OverridesStorageTestCase):
    def test_every_center_has_its_own_folder(self):
        first = get_template_override_path(DOCX_FILE_NAME, 1)
        second = get_template_override_path(DOCX_FILE_NAME, 2)

        self.assertEqual(first, self.center_dir(1) / DOCX_FILE_NAME)
        self.assertEqual(second, self.center_dir(2) / DOCX_FILE_NAME)
        self.assertNotEqual(first.parent, second.parent)

    def test_a_file_name_cannot_leave_the_center_folder(self):
        with self.assertRaises(ValueError):
            get_template_override_path("../center-2/082у_шаблон.docx", 1)

    def test_a_center_id_must_be_a_positive_number(self):
        for center_id in (0, -1):
            with self.subTest(center_id=center_id):
                with self.assertRaises(ValueError):
                    get_template_override_path(DOCX_FILE_NAME, center_id)

    def test_has_override_answers_for_one_center_only(self):
        write_docx(self.center_dir(1) / DOCX_FILE_NAME, "<w:t>копия центра 1</w:t>")

        self.assertTrue(template_has_override(DOCX_FILE_NAME, 1))
        self.assertFalse(template_has_override(DOCX_FILE_NAME, 2))
        self.assertFalse(template_has_override(DOCX_FILE_NAME, None))

    def test_override_folders_are_found_by_name(self):
        (self.center_dir(3)).mkdir()
        (self.center_dir(1)).mkdir()
        (self.storage_root / "center-x").mkdir()
        (self.storage_root / SHARED_OVERRIDES_BACKUP_FOLDER).mkdir()
        (self.storage_root / "center-2").write_text("файл, а не папка", encoding="utf-8")

        self.assertEqual(center_ids_with_override_folders(), [1, 3])


class ResolveTemplateFileTests(OverridesStorageTestCase):
    def make_template(self, *, file_path: Path | None = None) -> SimpleNamespace:
        bundled = TEMPLATES_DIR / DOCX_FILE_NAME
        return SimpleNamespace(file_name=DOCX_FILE_NAME, file_path=str(file_path or bundled))

    def test_the_center_gets_its_own_copy_and_the_other_gets_the_bundled_file(self):
        own_copy = self.center_dir(1) / DOCX_FILE_NAME
        write_docx(own_copy, "<w:t>копия центра 1</w:t>")
        template = self.make_template()

        self.assertEqual(resolve_template_file(template, 1), own_copy)
        self.assertEqual(resolve_template_file(template, 2), (TEMPLATES_DIR / DOCX_FILE_NAME).resolve())

    def test_without_a_center_the_bundled_file_is_printed(self):
        write_docx(self.center_dir(1) / DOCX_FILE_NAME, "<w:t>копия центра 1</w:t>")

        self.assertEqual(
            resolve_template_file(self.make_template()),
            (TEMPLATES_DIR / DOCX_FILE_NAME).resolve(),
        )

    def test_a_catalog_path_inside_the_overrides_storage_is_not_trusted(self):
        """До разделения путь в базе указывал на общую копию: чужую копию не печатаем."""
        shared_copy = self.storage_root / DOCX_FILE_NAME
        write_docx(shared_copy, "<w:t>общая копия</w:t>")
        other_center_copy = self.center_dir(1) / DOCX_FILE_NAME
        write_docx(other_center_copy, "<w:t>копия центра 1</w:t>")

        for stale_path in (shared_copy, other_center_copy):
            with self.subTest(stale_path=stale_path):
                self.assertEqual(
                    resolve_template_file(self.make_template(file_path=stale_path), 2),
                    (TEMPLATES_DIR / DOCX_FILE_NAME).resolve(),
                )


class SplitSharedOverridesTests(OverridesStorageTestCase):
    def backup_dir(self) -> Path:
        return self.storage_root.resolve() / SHARED_OVERRIDES_BACKUP_FOLDER

    def test_a_shared_copy_goes_to_every_center_and_the_original_to_the_backup(self):
        write_docx(self.storage_root / DOCX_FILE_NAME, "<w:t>общая копия</w:t>")

        split = split_shared_template_overrides([1, 2, 3])

        self.assertEqual(split, [DOCX_FILE_NAME])
        for center_id in (1, 2, 3):
            copy = self.center_dir(center_id) / DOCX_FILE_NAME
            self.assertTrue(copy.is_file())
            self.assertTrue(template_catalog.docx_text_contains(copy, "общая копия"))
        self.assertFalse((self.storage_root / DOCX_FILE_NAME).exists())
        self.assertTrue((self.backup_dir() / DOCX_FILE_NAME).is_file())

    def test_the_copies_of_the_centers_do_not_share_a_file(self):
        write_docx(self.storage_root / DOCX_FILE_NAME, "<w:t>общая копия</w:t>")

        split_shared_template_overrides([1, 2])
        write_docx(self.center_dir(1) / DOCX_FILE_NAME, "<w:t>правка центра 1</w:t>")

        self.assertTrue(template_catalog.docx_text_contains(self.center_dir(2) / DOCX_FILE_NAME, "общая копия"))

    def test_retired_and_unfinished_files_are_only_moved_to_the_backup(self):
        retired = self.storage_root / f"{DOCX_FILE_NAME}.retired-20261001000000"
        uploading = self.storage_root / f"{DOCX_FILE_NAME}.uploading"
        retired.write_bytes(b"retired")
        uploading.write_bytes(b"uploading")

        split_shared_template_overrides([1, 2])

        self.assertEqual(center_ids_with_override_folders(), [])
        self.assertTrue((self.backup_dir() / retired.name).is_file())
        self.assertTrue((self.backup_dir() / uploading.name).is_file())

    def test_a_copy_the_center_already_has_is_not_overwritten(self):
        write_docx(self.storage_root / DOCX_FILE_NAME, "<w:t>общая копия</w:t>")
        write_docx(self.center_dir(2) / DOCX_FILE_NAME, "<w:t>своя копия центра 2</w:t>")

        split_shared_template_overrides([1, 2])

        self.assertTrue(
            template_catalog.docx_text_contains(self.center_dir(2) / DOCX_FILE_NAME, "своя копия центра 2")
        )
        self.assertTrue(template_catalog.docx_text_contains(self.center_dir(1) / DOCX_FILE_NAME, "общая копия"))

    def test_the_second_run_changes_nothing(self):
        write_docx(self.storage_root / DOCX_FILE_NAME, "<w:t>общая копия</w:t>")
        split_shared_template_overrides([1, 2])
        write_docx(self.center_dir(1) / DOCX_FILE_NAME, "<w:t>правка центра 1</w:t>")

        self.assertEqual(split_shared_template_overrides([1, 2]), [])

        self.assertTrue(template_catalog.docx_text_contains(self.center_dir(1) / DOCX_FILE_NAME, "правка центра 1"))

    def test_a_backup_with_the_same_name_is_not_overwritten(self):
        self.backup_dir().mkdir()
        (self.backup_dir() / DOCX_FILE_NAME).write_bytes(b"prior backup")
        write_docx(self.storage_root / DOCX_FILE_NAME, "<w:t>общая копия</w:t>")

        split_shared_template_overrides([1])

        self.assertEqual((self.backup_dir() / DOCX_FILE_NAME).read_bytes(), b"prior backup")
        self.assertEqual(len(list(self.backup_dir().glob(f"{DOCX_FILE_NAME}.*"))), 1)

    def test_nothing_is_moved_when_there_are_no_centers(self):
        write_docx(self.storage_root / DOCX_FILE_NAME, "<w:t>общая копия</w:t>")

        self.assertEqual(split_shared_template_overrides([]), [])

        self.assertTrue((self.storage_root / DOCX_FILE_NAME).is_file())
        self.assertFalse(self.backup_dir().exists())

    def test_a_file_that_could_not_be_copied_stays_for_the_next_start(self):
        write_docx(self.storage_root / DOCX_FILE_NAME, "<w:t>общая копия</w:t>")

        with mock.patch.object(template_catalog.shutil, "copy2", side_effect=OSError("диск занят")):
            with self.assertLogs(template_catalog.logger, level="ERROR"):
                self.assertEqual(split_shared_template_overrides([1, 2]), [])

        self.assertTrue((self.storage_root / DOCX_FILE_NAME).is_file())
        self.assertFalse(self.backup_dir().exists())
        self.assertEqual(split_shared_template_overrides([1, 2]), [DOCX_FILE_NAME])


class OutdatedOverridesPerCenterTests(OverridesStorageTestCase):
    def test_an_outdated_copy_is_retired_only_in_the_center_that_holds_it(self):
        outdated = self.center_dir(1) / GTO_FILE_NAME
        current = self.center_dir(2) / GTO_FILE_NAME
        write_docx(outdated, "<w:t>[LastName]</w:t>")
        write_docx(current, "<w:t>[GtoAthleteRegistryNumber]</w:t>")

        retire_outdated_template_overrides()

        self.assertFalse(outdated.exists())
        self.assertEqual(len(list(self.center_dir(1).glob(f"{GTO_FILE_NAME}.retired-*"))), 1)
        self.assertTrue(current.is_file())
        self.assertEqual(list(self.center_dir(2).glob(f"{GTO_FILE_NAME}.retired-*")), [])


class TemplateRoutesPerCenterTests(OverridesStorageTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        with Session(self.engine) as db:
            first = Center(code="route-first", name="Первый")
            second = Center(code="route-second", name="Второй")
            db.add_all([first, second])
            db.add(
                DocumentTemplate(
                    code="route-082",
                    name="082у",
                    file_name=DOCX_FILE_NAME,
                    file_path=str(TEMPLATES_DIR / DOCX_FILE_NAME),
                    template_type="docx",
                    output_format="docx",
                    is_active=True,
                )
            )
            db.commit()
            self.first_center_id = first.id
            self.second_center_id = second.id
            self.template_id = db.query(DocumentTemplate).one().id

    def staff_of(self, center_id: int | None) -> SimpleNamespace:
        """Сотрудник одного центра; без центра — админ, который видит все."""
        return self.staff_with_centers(center_id) if center_id is not None else SimpleNamespace(
            pinned_center_id=None, sees_all_centers=True, work_centers=[]
        )

    def staff_with_centers(self, primary_center_id: int, *extra_center_ids: int) -> SimpleNamespace:
        """Сотрудник с основным и дополнительными центрами."""
        return SimpleNamespace(
            pinned_center_id=primary_center_id,
            sees_all_centers=False,
            work_centers=[SimpleNamespace(id=center_id) for center_id in (primary_center_id, *extra_center_ids)],
        )

    def upload(self, content: bytes) -> UploadFile:
        return UploadFile(filename=DOCX_FILE_NAME, file=BytesIO(content))

    def has_override_in_list(self, db: Session, center_id: int | None) -> bool:
        listed = list_document_templates(center_id, db)
        return next(item for item in listed if item.id == self.template_id).has_override

    def test_an_upload_lands_only_in_the_folder_of_its_center(self):
        with Session(self.engine) as db:
            response = replace_document_template(
                self.template_id,
                self.upload(b"copy of the first center"),
                None,
                self.staff_of(self.first_center_id),
                db,
            )

            self.assertTrue(response.has_override)
            self.assertEqual(
                (self.center_dir(self.first_center_id) / DOCX_FILE_NAME).read_bytes(),
                b"copy of the first center",
            )
            self.assertFalse(self.center_dir(self.second_center_id).exists())
            self.assertFalse((self.storage_root / DOCX_FILE_NAME).exists())
            self.assertTrue(self.has_override_in_list(db, self.first_center_id))
            self.assertFalse(self.has_override_in_list(db, self.second_center_id))
            self.assertFalse(self.has_override_in_list(db, None))

    def test_an_upload_does_not_change_the_shared_catalog_row(self):
        with Session(self.engine) as db:
            replace_document_template(
                self.template_id,
                self.upload(b"copy"),
                None,
                self.staff_of(self.first_center_id),
                db,
            )

            template = db.get(DocumentTemplate, self.template_id)
            self.assertEqual(Path(template.file_path), TEMPLATES_DIR / DOCX_FILE_NAME)
            self.assertEqual(
                resolve_template_file(template, self.second_center_id),
                (TEMPLATES_DIR / DOCX_FILE_NAME).resolve(),
            )

    def test_the_centers_keep_their_own_versions_side_by_side(self):
        with Session(self.engine) as db:
            for center_id, content in ((self.first_center_id, b"first"), (self.second_center_id, b"second")):
                replace_document_template(self.template_id, self.upload(content), None, self.staff_of(center_id), db)

            self.assertEqual((self.center_dir(self.first_center_id) / DOCX_FILE_NAME).read_bytes(), b"first")
            self.assertEqual((self.center_dir(self.second_center_id) / DOCX_FILE_NAME).read_bytes(), b"second")

    def test_reset_returns_the_bundled_file_for_one_center_only(self):
        with Session(self.engine) as db:
            for center_id in (self.first_center_id, self.second_center_id):
                replace_document_template(
                    self.template_id,
                    self.upload(b"copy"),
                    None,
                    self.staff_of(center_id),
                    db,
                )

            response = reset_document_template(self.template_id, None, self.staff_of(self.first_center_id), db)

            self.assertFalse(response.has_override)
            self.assertFalse((self.center_dir(self.first_center_id) / DOCX_FILE_NAME).exists())
            self.assertTrue((self.center_dir(self.second_center_id) / DOCX_FILE_NAME).is_file())
            self.assertTrue(self.has_override_in_list(db, self.second_center_id))

    def test_a_pinned_employee_cannot_touch_another_center(self):
        with Session(self.engine) as db:
            for action in (
                lambda: replace_document_template(
                    self.template_id,
                    self.upload(b"copy"),
                    self.second_center_id,
                    self.staff_of(self.first_center_id),
                    db,
                ),
                lambda: reset_document_template(
                    self.template_id,
                    self.second_center_id,
                    self.staff_of(self.first_center_id),
                    db,
                ),
                lambda: open_document_template(
                    self.template_id,
                    self.second_center_id,
                    self.staff_of(self.first_center_id),
                    db,
                ),
            ):
                with self.subTest(action=action):
                    with self.assertRaises(HTTPException) as raised:
                        action()
                    self.assertEqual(raised.exception.status_code, 403)
            self.assertFalse(self.center_dir(self.second_center_id).exists())

    def test_an_employee_with_extra_centers_works_in_each_of_them_but_not_in_others(self):
        with Session(self.engine) as db:
            third = Center(code="route-third", name="Третий")
            db.add(third)
            db.commit()
            staff = self.staff_with_centers(self.first_center_id, self.second_center_id)

            # Центр не назван — основной; назван дополнительный — работает в нём.
            replace_document_template(self.template_id, self.upload(b"primary"), None, staff, db)
            replace_document_template(self.template_id, self.upload(b"extra"), self.second_center_id, staff, db)

            self.assertEqual((self.center_dir(self.first_center_id) / DOCX_FILE_NAME).read_bytes(), b"primary")
            self.assertEqual((self.center_dir(self.second_center_id) / DOCX_FILE_NAME).read_bytes(), b"extra")
            with self.assertRaises(HTTPException) as raised:
                replace_document_template(self.template_id, self.upload(b"alien"), third.id, staff, db)
            self.assertEqual(raised.exception.status_code, 403)
            self.assertFalse(self.center_dir(third.id).exists())

    def test_an_employee_without_any_center_is_not_restricted_to_one(self):
        """Старая учётная запись без центра: ограничивать нечем, центр назван запросом."""
        legacy = SimpleNamespace(pinned_center_id=None, sees_all_centers=False, work_centers=[])
        with Session(self.engine) as db:
            replace_document_template(
                self.template_id, self.upload(b"copy"), self.second_center_id, legacy, db
            )

            self.assertTrue((self.center_dir(self.second_center_id) / DOCX_FILE_NAME).is_file())

    def test_an_admin_must_name_the_center_for_an_upload_and_a_reset(self):
        with Session(self.engine) as db:
            admin = self.staff_of(None)
            for action in (
                lambda: replace_document_template(self.template_id, self.upload(b"copy"), None, admin, db),
                lambda: reset_document_template(self.template_id, None, admin, db),
            ):
                with self.subTest(action=action):
                    with self.assertRaises(HTTPException) as raised:
                        action()
                    self.assertEqual(raised.exception.status_code, 400)
            self.assertEqual(list(self.storage_root.iterdir()), [])

    def test_an_unknown_center_is_refused(self):
        with Session(self.engine) as db:
            with self.assertRaises(HTTPException) as raised:
                replace_document_template(self.template_id, self.upload(b"copy"), 999, self.staff_of(None), db)
            self.assertEqual(raised.exception.status_code, 404)
            self.assertEqual(list(self.storage_root.iterdir()), [])

    def test_an_admin_opens_the_file_of_the_chosen_center(self):
        with Session(self.engine) as db:
            replace_document_template(
                self.template_id,
                self.upload(b"copy of the first center"),
                None,
                self.staff_of(self.first_center_id),
                db,
            )
            admin = self.staff_of(None)

            first = open_document_template(self.template_id, self.first_center_id, admin, db)
            second = open_document_template(self.template_id, self.second_center_id, admin, db)

            self.assertEqual(Path(first.path), self.center_dir(self.first_center_id) / DOCX_FILE_NAME)
            self.assertEqual(Path(second.path), (TEMPLATES_DIR / DOCX_FILE_NAME).resolve())

    def test_a_pinned_employee_opens_the_file_of_the_own_center_without_naming_it(self):
        with Session(self.engine) as db:
            staff = self.staff_of(self.first_center_id)
            replace_document_template(self.template_id, self.upload(b"copy"), None, staff, db)

            opened = open_document_template(self.template_id, None, staff, db)

            self.assertEqual(Path(opened.path), self.center_dir(self.first_center_id) / DOCX_FILE_NAME)


if __name__ == "__main__":
    unittest.main()
