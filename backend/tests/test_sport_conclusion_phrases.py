from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
import app.db.init_db as init_db_module  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.template_phrase import TemplatePhrase  # noqa: E402
from app.services.document_generator import EKG_STANDARD_CONCLUSION  # noqa: E402


class SportConclusionPhrasesTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_standard_ekg_conclusion_is_in_sport_dictionary_once(self):
        original_engine = init_db_module.engine
        original_session_local = init_db_module.SessionLocal
        init_db_module.engine = self.engine
        init_db_module.SessionLocal = self.Session
        try:
            init_db_module.seed_sport_conclusion_phrases()
            init_db_module.seed_sport_conclusion_phrases()
        finally:
            init_db_module.engine = original_engine
            init_db_module.SessionLocal = original_session_local

        with self.Session() as db:
            texts = db.scalars(
                select(TemplatePhrase.text).where(
                    TemplatePhrase.code == "sport_conclusion",
                    TemplatePhrase.text == EKG_STANDARD_CONCLUSION,
                )
            ).all()
        self.assertEqual(len(texts), 1)


if __name__ == "__main__":
    unittest.main()
