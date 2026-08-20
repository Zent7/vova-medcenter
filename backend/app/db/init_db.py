from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.models.blank_form import (
    BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
    BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE,
    BLANK_TYPE_GUARD_MEDICAL_CERTIFICATE,
    BLANK_TYPE_LMK_MEDICAL_CERTIFICATE,
    BLANK_TYPE_TRACTOR_MEDICAL_CERTIFICATE,
    NUMBERED_BLANK_TYPES,
)
from app.models import *  # noqa: F401,F403
from app.services.seed import seed_reference_data
from sqlalchemy import inspect, select, text


LEGACY_IMPORT_COLUMNS = {
    "clients": "legacy_source_id",
    "services": "legacy_source_id",
    "encounters": "legacy_source_id",
    "encounter_services": "legacy_source_id",
    "payments": "legacy_source_id",
}

CLIENT_PROFILE_COLUMNS = {
    "email": "VARCHAR(255)",
    "document_type": "VARCHAR(80)",
    "document_series": "VARCHAR(40)",
    "document_number": "VARCHAR(80)",
    "document_issued_by": "VARCHAR(500)",
    "document_issued_date": "DATE",
    "registration_text": "TEXT",
    "admission_category": "VARCHAR(255)",
    "reference_number": "VARCHAR(80)",
    "doctor_gynecologist": "VARCHAR(80)",
    "doctor_stomatologist": "VARCHAR(80)",
    "doctor_dermatologist": "VARCHAR(80)",
    "doctor_neurologist": "VARCHAR(80)",
    "doctor_surgeon": "VARCHAR(80)",
    "doctor_otolaryngologist": "VARCHAR(80)",
    "doctor_ophthalmologist": "VARCHAR(80)",
    "doctor_therapist": "VARCHAR(80)",
    "doctor_psychiatrist": "VARCHAR(80)",
    "doctor_infectionist": "VARCHAR(80)",
    "doctor_phthisiatrician": "VARCHAR(80)",
    "doctor_uzist": "VARCHAR(80)",
    "indications": "TEXT",
    "encounter_date_text": "VARCHAR(120)",
    "card_number": "VARCHAR(80)",
    "journal_number": "VARCHAR(80)",
    "no_number": "VARCHAR(80)",
    "flg": "VARCHAR(80)",
    "profession": "VARCHAR(255)",
    "work_place": "VARCHAR(255)",
    "organization": "VARCHAR(255)",
    "mkb10": "VARCHAR(80)",
    "real_date_text": "VARCHAR(120)",
    "legacy_payload_json": "JSON",
}

ENCOUNTER_PROFILE_COLUMNS = {
    "suppressed_doctor_role_ids": "JSON",
}

SPORT_CONCLUSION_PHRASES = [
    "Допущен к участию в соревнованиях",
    "Допущен к участию в соревнованиях по спорту \"Трофи-Рейд-Квадроциклы\".",
    "Допущен к участию в соревнованиях по гиревому спорту.",
    "Допущен к участию в соревнованиях по гребле на дистанцию 70 км",
    "Допущен к участию в соревнованиях по бегу на дистанцию 10 км",
    "Допущен к участию в соревнованиях по бегу с препятствиями на дистанции до 10 км",
    "Допущен к участию в соревнованиях по велоспорту на дистанцию 40 км",
    "Допущен к участию в соревнованиях по футболу",
    "Допущена к занятиям спортом, участию в соревнованиях по велоспорту на дистанции до 20 км",
    "Допущена к участию в соревнованиях по бегу",
    "Допущена к участию в соревнованиях по бегу на дистанции 10 км",
    "Допущена к участию в соревнованиях по бегу на дистанции 5 км",
    "Допущена к участию в соревнованиях по спорту ушу.",
    "Допущена к фигурному катанию",
    "Допущен к соревнованиям по велоспорту на дистанции 40 км",
    "Допущен к участию в соревнованиях по функциональному многоборью",
    "Допущена к соревнованиям на велогонку на дистанции 20 км и к соревнованиям по бегу на 10 км",
    "Допущена к соревнованиям по велоспорту на дистанции 20 км и к соревнованиям по бегу на 10 км",
    "Физической культуры по программе ВУЗа допущен; группа здоровья - основная",
    "Допущен к соревнованиям по фитнесу и бодибилдингу",
    "Допущен к соревнованиям по практической стрельбе",
    "Допущен к соревнованиям по спортивному парапланеризму",
    "Допущен к соревнованиям по спортивному туризму",
    "Допущен к соревнованиям по спортивному туризму на средствах передвижения",
    "Допущен к соревнованиям по стрельбе",
    "Допущен к соревнованиям по кэндо",
    "Допущен к соревнованиям по спортивным бальным танцам",
    "Допущен к соревнованиям по тхэквондо",
]


def add_integer_column_if_missing(connection, dialect: str, table_name: str, column_name: str) -> None:
    if dialect == "postgresql":
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} INTEGER"))
    else:
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} INTEGER"))


def add_column_if_missing(connection, dialect: str, table_name: str, column_name: str, column_type: str) -> None:
    if dialect == "postgresql":
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_type}"))
    else:
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))


def create_unique_index_if_possible(connection, dialect: str, table_name: str, column_name: str) -> None:
    index_name = f"ix_{table_name}_{column_name}"
    if dialect in {"postgresql", "sqlite"}:
        connection.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table_name}({column_name})"))


def create_index_if_possible(connection, dialect: str, index_name: str, table_name: str, columns: str) -> None:
    if dialect in {"postgresql", "sqlite"}:
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({columns})"))


def ensure_client_patient_numbers() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("clients"):
        return

    columns = {column["name"] for column in inspector.get_columns("clients")}
    dialect = engine.dialect.name
    with engine.begin() as connection:
        if "patient_number" not in columns:
            add_integer_column_if_missing(connection, dialect, "clients", "patient_number")

        rows = connection.execute(
            text("SELECT id FROM clients WHERE patient_number IS NULL ORDER BY id")
        ).mappings().all()
        for index, row in enumerate(rows, start=1):
            next_number = connection.execute(text("SELECT COALESCE(MAX(patient_number), 0) + 1 FROM clients")).scalar_one()
            connection.execute(
                text("UPDATE clients SET patient_number = :patient_number WHERE id = :id"),
                {"patient_number": next_number or index, "id": row["id"]},
            )

        create_unique_index_if_possible(connection, dialect, "clients", "patient_number")


def ensure_legacy_import_columns() -> None:
    inspector = inspect(engine)
    dialect = engine.dialect.name
    with engine.begin() as connection:
        for table_name, column_name in LEGACY_IMPORT_COLUMNS.items():
            if not inspector.has_table(table_name):
                continue

            columns = {column["name"] for column in inspector.get_columns(table_name)}
            if column_name not in columns:
                add_integer_column_if_missing(connection, dialect, table_name, column_name)

            create_unique_index_if_possible(connection, dialect, table_name, column_name)


def ensure_client_profile_columns() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("clients"):
        return

    columns = {column["name"] for column in inspector.get_columns("clients")}
    dialect = engine.dialect.name
    with engine.begin() as connection:
        for column_name, column_type in CLIENT_PROFILE_COLUMNS.items():
            if column_name not in columns:
                add_column_if_missing(connection, dialect, "clients", column_name, column_type)

        create_index_if_possible(connection, dialect, "ix_clients_document_series", "clients", "document_series")
        create_index_if_possible(connection, dialect, "ix_clients_document_number", "clients", "document_number")
        create_index_if_possible(connection, dialect, "ix_clients_reference_number", "clients", "reference_number")
        create_index_if_possible(connection, dialect, "ix_clients_card_number", "clients", "card_number")
        create_index_if_possible(connection, dialect, "ix_clients_organization", "clients", "organization")
        create_index_if_possible(connection, dialect, "ix_clients_mkb10", "clients", "mkb10")
        create_index_if_possible(connection, dialect, "ix_clients_profession", "clients", "profession")
        create_index_if_possible(connection, dialect, "ix_clients_work_place", "clients", "work_place")
        create_index_if_possible(
            connection,
            dialect,
            "ix_clients_document_identity",
            "clients",
            "document_series, document_number",
        )
        create_index_if_possible(
            connection,
            dialect,
            "ix_clients_full_name_birth",
            "clients",
            "last_name, first_name, middle_name, birth_date",
        )


def ensure_encounter_profile_columns() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("encounters"):
        return

    columns = {column["name"] for column in inspector.get_columns("encounters")}
    dialect = engine.dialect.name
    with engine.begin() as connection:
        for column_name, column_type in ENCOUNTER_PROFILE_COLUMNS.items():
            if column_name not in columns:
                add_column_if_missing(connection, dialect, "encounters", column_name, column_type)


def ensure_blank_form_tables() -> None:
    inspector = inspect(engine)
    blank_table_names = {"blank_types", "blank_batches", "blank_forms"}
    existing_blank_tables = {name for name in blank_table_names if inspector.has_table(name)}
    if existing_blank_tables != blank_table_names:
        blank_tables = [Base.metadata.tables[name] for name in sorted(blank_table_names) if name in Base.metadata.tables]
        Base.metadata.create_all(engine, tables=blank_tables, checkfirst=True)

    dialect = engine.dialect.name
    with engine.begin() as connection:
        generated_columns = {column["name"] for column in inspector.get_columns("generated_documents")} if inspector.has_table("generated_documents") else set()
        if inspector.has_table("generated_documents"):
            if "blank_form_id" not in generated_columns:
                add_integer_column_if_missing(connection, dialect, "generated_documents", "blank_form_id")
            if "blank_number_snapshot" not in generated_columns:
                add_column_if_missing(connection, dialect, "generated_documents", "blank_number_snapshot", "VARCHAR(80)")
            if "cancelled_at" not in generated_columns:
                add_column_if_missing(connection, dialect, "generated_documents", "cancelled_at", "TIMESTAMP WITH TIME ZONE")
            if "cancelled_by_user_id" not in generated_columns:
                add_integer_column_if_missing(connection, dialect, "generated_documents", "cancelled_by_user_id")
            if "cancelled_reason" not in generated_columns:
                add_column_if_missing(connection, dialect, "generated_documents", "cancelled_reason", "VARCHAR(500)")
            if "file_deleted_at" not in generated_columns:
                add_column_if_missing(connection, dialect, "generated_documents", "file_deleted_at", "TIMESTAMP WITH TIME ZONE")
            if "file_delete_reason" not in generated_columns:
                add_column_if_missing(connection, dialect, "generated_documents", "file_delete_reason", "VARCHAR(500)")
            create_index_if_possible(connection, dialect, "ix_generated_documents_blank_form_id", "generated_documents", "blank_form_id")
            create_index_if_possible(connection, dialect, "ix_generated_documents_blank_number_snapshot", "generated_documents", "blank_number_snapshot")

        client_document_columns = {column["name"] for column in inspector.get_columns("client_documents")} if inspector.has_table("client_documents") else set()
        if inspector.has_table("client_documents"):
            if "blank_form_id" not in client_document_columns:
                add_integer_column_if_missing(connection, dialect, "client_documents", "blank_form_id")
            if "blank_number_snapshot" not in client_document_columns:
                add_column_if_missing(connection, dialect, "client_documents", "blank_number_snapshot", "VARCHAR(80)")
            create_index_if_possible(connection, dialect, "ix_client_documents_blank_form_id", "client_documents", "blank_form_id")
            create_index_if_possible(connection, dialect, "ix_client_documents_blank_number_snapshot", "client_documents", "blank_number_snapshot")


def ensure_document_template_blank_columns() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("document_templates"):
        return

    columns = {column["name"] for column in inspector.get_columns("document_templates")}
    dialect = engine.dialect.name
    with engine.begin() as connection:
        if "requires_numbered_blank" not in columns:
            add_column_if_missing(
                connection,
                dialect,
                "document_templates",
                "requires_numbered_blank",
                "BOOLEAN DEFAULT FALSE",
            )
        if "blank_type" not in columns:
            add_column_if_missing(
                connection,
                dialect,
                "document_templates",
                "blank_type",
                "VARCHAR(80)",
            )
        create_index_if_possible(
            connection,
            dialect,
            "ix_document_templates_blank_type",
            "document_templates",
            "blank_type",
        )

        blank_type_updates = [
            (
                BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE,
                """
                lower(coalesce(name, '')) LIKE '%гимс%'
                OR lower(coalesce(file_name, '')) LIKE '%гимс%'
                OR lower(coalesce(code, '')) LIKE '%gims%'
                OR lower(coalesce(name, '')) LIKE '%gims%'
                OR lower(coalesce(file_name, '')) LIKE '%gims%'
                """,
            ),
            (
                BLANK_TYPE_LMK_MEDICAL_CERTIFICATE,
                """
                lower(coalesce(name, '')) LIKE '%лмк%'
                OR lower(coalesce(file_name, '')) LIKE '%лмк%'
                OR lower(coalesce(code, '')) LIKE '%lmk%'
                OR lower(coalesce(name, '')) LIKE '%lmk%'
                OR lower(coalesce(file_name, '')) LIKE '%lmk%'
                """,
            ),
            (
                BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                """
                lower(coalesce(name, '')) LIKE '%вод%'
                OR lower(coalesce(file_name, '')) LIKE '%вод%'
                OR lower(coalesce(code, '')) LIKE '%driver%'
                OR lower(coalesce(name, '')) LIKE '%driver%'
                OR lower(coalesce(file_name, '')) LIKE '%driver%'
                """,
            ),
            (
                BLANK_TYPE_TRACTOR_MEDICAL_CERTIFICATE,
                """
                lower(coalesce(name, '')) LIKE '%трактор%'
                OR lower(coalesce(file_name, '')) LIKE '%трактор%'
                OR lower(coalesce(code, '')) LIKE '%tractor%'
                OR lower(coalesce(name, '')) LIKE '%tractor%'
                OR lower(coalesce(file_name, '')) LIKE '%tractor%'
                OR lower(coalesce(name, '')) LIKE '%071%'
                OR lower(coalesce(file_name, '')) LIKE '%071%'
                """,
            ),
            (
                BLANK_TYPE_GUARD_MEDICAL_CERTIFICATE,
                """
                lower(coalesce(name, '')) LIKE '%охран%'
                OR lower(coalesce(file_name, '')) LIKE '%охран%'
                OR lower(coalesce(code, '')) LIKE '%guard%'
                OR lower(coalesce(name, '')) LIKE '%guard%'
                OR lower(coalesce(file_name, '')) LIKE '%guard%'
                OR lower(coalesce(name, '')) LIKE '%чод%'
                OR lower(coalesce(file_name, '')) LIKE '%чод%'
                OR lower(coalesce(name, '')) LIKE '%002%'
                OR lower(coalesce(file_name, '')) LIKE '%002%'
                """,
            ),
        ]
        for blank_type, predicate in blank_type_updates:
            connection.execute(
                text(
                    f"""
                    UPDATE document_templates
                    SET requires_numbered_blank = TRUE,
                        blank_type = :blank_type
                    WHERE ({predicate})
                    AND (
                        coalesce(requires_numbered_blank, FALSE) = FALSE
                        OR blank_type IS NULL
                        OR blank_type = ''
                    )
                    """
                ),
                {"blank_type": blank_type},
            )


def seed_blank_types() -> None:
    if not inspect(engine).has_table("blank_types"):
        return

    with SessionLocal() as db:
        for code, name in NUMBERED_BLANK_TYPES:
            existing = db.execute(select(BlankType).where(BlankType.code == code)).scalar_one_or_none()
            if existing is None:
                db.add(BlankType(code=code, name=name, is_active=True))
            else:
                existing.name = name
                existing.is_active = True
        db.flush()
        db.execute(
            text(
                """
                UPDATE blank_batches
                SET blank_type = CASE
                    WHEN coalesce(series, '') LIKE 'ЛМК%'
                        OR lower(coalesce(series, '')) LIKE 'лмк%'
                        OR lower(coalesce(series, '')) LIKE 'lmk%'
                        THEN :lmk_type
                    WHEN coalesce(series, '') LIKE 'ГИМС%'
                        OR lower(coalesce(series, '')) LIKE 'гимс%'
                        OR lower(coalesce(series, '')) LIKE 'gims%'
                        THEN :gims_type
                    ELSE blank_type
                END
                WHERE blank_type = :driver_type
                  AND (
                    coalesce(series, '') LIKE 'ЛМК%'
                    OR lower(coalesce(series, '')) LIKE 'лмк%'
                    OR lower(coalesce(series, '')) LIKE 'lmk%'
                    OR coalesce(series, '') LIKE 'ГИМС%'
                    OR lower(coalesce(series, '')) LIKE 'гимс%'
                    OR lower(coalesce(series, '')) LIKE 'gims%'
                  )
                """
            ),
            {
                "driver_type": BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                "gims_type": BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE,
                "lmk_type": BLANK_TYPE_LMK_MEDICAL_CERTIFICATE,
            },
        )
        db.execute(
            text(
                """
                UPDATE blank_forms
                SET blank_type = CASE
                    WHEN coalesce(series, '') LIKE 'ЛМК%'
                        OR lower(coalesce(series, '')) LIKE 'лмк%'
                        OR lower(coalesce(series, '')) LIKE 'lmk%'
                        THEN :lmk_type
                    WHEN coalesce(series, '') LIKE 'ГИМС%'
                        OR lower(coalesce(series, '')) LIKE 'гимс%'
                        OR lower(coalesce(series, '')) LIKE 'gims%'
                        THEN :gims_type
                    ELSE blank_type
                END
                WHERE blank_type = :driver_type
                  AND (
                    coalesce(series, '') LIKE 'ЛМК%'
                    OR lower(coalesce(series, '')) LIKE 'лмк%'
                    OR lower(coalesce(series, '')) LIKE 'lmk%'
                    OR coalesce(series, '') LIKE 'ГИМС%'
                    OR lower(coalesce(series, '')) LIKE 'гимс%'
                    OR lower(coalesce(series, '')) LIKE 'gims%'
                  )
                """
            ),
            {
                "driver_type": BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
                "gims_type": BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE,
                "lmk_type": BLANK_TYPE_LMK_MEDICAL_CERTIFICATE,
            },
        )
        db.commit()


def seed_sport_conclusion_phrases() -> None:
    if not inspect(engine).has_table("template_phrases"):
        return

    with SessionLocal() as db:
        for phrase_text in SPORT_CONCLUSION_PHRASES:
            exists = db.execute(
                select(TemplatePhrase).where(
                    TemplatePhrase.code == "sport_conclusion",
                    TemplatePhrase.text == phrase_text,
                )
            ).scalar_one_or_none()
            if exists is not None:
                continue
            db.add(
                TemplatePhrase(
                    code="sport_conclusion",
                    name=phrase_text[:100],
                    text=phrase_text,
                    is_default=False,
                    is_active=True,
                )
            )
        db.commit()


def init_db() -> None:
    Base.metadata.create_all(engine, checkfirst=True)
    ensure_client_patient_numbers()
    ensure_legacy_import_columns()
    ensure_client_profile_columns()
    ensure_encounter_profile_columns()
    ensure_blank_form_tables()
    ensure_document_template_blank_columns()
    seed_blank_types()
    seed_sport_conclusion_phrases()
    with SessionLocal() as db:
        seed_reference_data(db)
