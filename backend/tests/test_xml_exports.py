from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.document_template import DocumentTemplate  # noqa: E402
from app.models.generated_document import GeneratedDocument  # noqa: E402
from app.services.document_generator import generate_document  # noqa: E402
from app.services.xml_exports import (  # noqa: E402
    build_xml_export_archive,
    cleanup_old_xml_exports,
    delete_xml_day,
    delete_xml_document_by_id,
    list_xml_export_days,
)


class XmlExportsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_dir = Path(self.temp_dir.name) / "generated"
        self.templates_dir = Path(self.temp_dir.name) / "templates"
        self.templates_dir.mkdir(parents=True)

        self.original_generated_dir = settings.generated_documents_dir
        self.original_timezone = settings.xml_exports_timezone
        self.original_retention = settings.xml_exports_retention_days
        settings.generated_documents_dir = str(self.storage_dir)
        settings.xml_exports_timezone = "Europe/Moscow"
        settings.xml_exports_retention_days = 30

        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        settings.generated_documents_dir = self.original_generated_dir
        settings.xml_exports_timezone = self.original_timezone
        settings.xml_exports_retention_days = self.original_retention
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        self.temp_dir.cleanup()

    def session(self):
        return self.Session()

    def add_template(self, db, template_type="xml", file_path=None):
        template = DocumentTemplate(
            code=f"{template_type}_{len(db.identity_map)}",
            name=f"{template_type} template",
            file_name=Path(file_path or f"template.{template_type}").name,
            file_path=str(file_path or self.templates_dir / f"template.{template_type}"),
            template_type=template_type,
            output_format=template_type,
            is_active=True,
        )
        db.add(template)
        db.flush()
        return template

    def add_xml_document(self, db, *, generated_at, file_name="export.xml", content="<root/>"):
        template = self.add_template(db, "xml", self.templates_dir / f"source_{file_name}")
        path = self.storage_dir / "xml" / generated_at.astimezone(ZoneInfo("Europe/Moscow")).date().isoformat() / file_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        document = GeneratedDocument(
            client_id=1,
            template_id=template.id,
            file_name=file_name,
            file_path=str(path),
            generated_at=generated_at,
        )
        db.add(document)
        db.flush()
        return document, path

    def test_generated_xml_is_saved_under_day_folder(self):
        template_path = self.templates_dir / "driver.xml"
        template_path.write_text("<root>{{ClientCalc}}</root>", encoding="utf-8")

        with self.session() as db:
            template = self.add_template(db, "xml", template_path)
            client = Client(
                patient_number=1,
                last_name="Ivanov",
                first_name="Ivan",
                middle_name="Ivanovich",
                birth_date=date(1990, 1, 1),
            )
            db.add(client)
            db.commit()

            result = generate_document(db, template_id=template.id, template_code=None, client_id=client.id, encounter_id=None)
            db.commit()

        expected_day = datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()
        output_path = Path(result.output_file_path)
        self.assertEqual(output_path.parent, self.storage_dir / "xml" / expected_day)
        self.assertTrue(output_path.is_file())

    def test_day_archive_skips_deleted_and_missing_files(self):
        with self.session() as db:
            available, _ = self.add_xml_document(
                db,
                generated_at=datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
                file_name="available.xml",
                content="<available/>",
            )
            missing, missing_path = self.add_xml_document(
                db,
                generated_at=datetime(2026, 7, 10, 10, tzinfo=timezone.utc),
                file_name="missing.xml",
            )
            missing_path.unlink()
            missing.file_deleted_at = datetime.now(timezone.utc)
            missing.file_delete_reason = "manual"
            db.commit()

            days = list_xml_export_days(db)
            archive_name, content = build_xml_export_archive(db, "2026-07-10")

        self.assertEqual(days[0].available_count, 1)
        self.assertEqual(days[0].deleted_count, 1)
        self.assertEqual(archive_name, "xml-export-2026-07-10.zip")
        self.assertIn(b"available.xml", content)
        self.assertNotIn(b"missing.xml", content)
        self.assertEqual(available.file_name, "available.xml")

    def test_delete_single_xml_marks_record_and_removes_file(self):
        with self.session() as db:
            document, path = self.add_xml_document(
                db,
                generated_at=datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            )
            db.commit()

            result = delete_xml_document_by_id(db, document.id)
            db.commit()
            db.refresh(document)

        self.assertEqual(result.deleted_count, 1)
        self.assertFalse(path.exists())
        self.assertIsNotNone(document.file_deleted_at)
        self.assertEqual(document.file_delete_reason, "manual")

    def test_delete_day_marks_all_day_xml_files(self):
        with self.session() as db:
            first, first_path = self.add_xml_document(
                db,
                generated_at=datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
                file_name="first.xml",
            )
            second, second_path = self.add_xml_document(
                db,
                generated_at=datetime(2026, 7, 10, 11, tzinfo=timezone.utc),
                file_name="second.xml",
            )
            db.commit()

            result = delete_xml_day(db, "2026-07-10")
            db.commit()
            db.refresh(first)
            db.refresh(second)

        self.assertEqual(result.deleted_count, 2)
        self.assertFalse(first_path.exists())
        self.assertFalse(second_path.exists())
        self.assertIsNotNone(first.file_deleted_at)
        self.assertIsNotNone(second.file_deleted_at)

    def test_cleanup_removes_only_old_xml_exports(self):
        now = datetime.now(timezone.utc)
        old_at = now - timedelta(days=45)
        fresh_at = now - timedelta(days=5)
        with self.session() as db:
            old_xml, old_path = self.add_xml_document(db, generated_at=old_at, file_name="old.xml")
            fresh_xml, fresh_path = self.add_xml_document(db, generated_at=fresh_at, file_name="fresh.xml")
            docx_template = self.add_template(db, "docx", self.templates_dir / "source.docx")
            docx_path = self.storage_dir / "source.docx"
            docx_path.parent.mkdir(parents=True, exist_ok=True)
            docx_path.write_text("docx", encoding="utf-8")
            db.add(
                GeneratedDocument(
                    client_id=1,
                    template_id=docx_template.id,
                    file_name="source.docx",
                    file_path=str(docx_path),
                    generated_at=old_at,
                )
            )
            db.commit()

            result = cleanup_old_xml_exports(db, retention_days=30)
            db.commit()
            db.refresh(old_xml)
            db.refresh(fresh_xml)

        self.assertEqual(result.deleted_count, 1)
        self.assertFalse(old_path.exists())
        self.assertTrue(fresh_path.exists())
        self.assertTrue(docx_path.exists())
        self.assertEqual(old_xml.file_delete_reason, "retention")
        self.assertIsNone(fresh_xml.file_deleted_at)


if __name__ == "__main__":
    unittest.main()
