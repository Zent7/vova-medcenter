"""У каждого медцентра своя клиентская база.

Сотрудник видит клиентов своих центров. Сотрудник с несколькими центрами видит
базы всех своих центров и может завести клиента сразу в оба. Тёзка из чужого
центра заводиться не мешает, а обращение в центре делает клиента клиентом этого
центра.
"""

from __future__ import annotations

from datetime import date
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session


os.environ.setdefault("ALLOW_SQLITE", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes.clients import (  # noqa: E402
    create_client,
    list_clients,
    list_deleted_clients,
    search_clients,
    update_client,
)
from app.api.v1.routes.dashboard import get_dashboard_encounter_rows  # noqa: E402
from app.api.v1.routes.encounters import create_encounter  # noqa: E402
from app.api.v1.routes.imports import find_existing_client_for_import  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.client import Client, client_centers  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.schemas.client import ClientCreate, ClientUpdate  # noqa: E402
from app.schemas.encounter import EncounterCreate  # noqa: E402


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "migrations" / "versions" / "20261007_0024_add_client_centers.py"
)


def client_payload(last_name: str, **extra) -> ClientCreate:
    return ClientCreate(
        last_name=last_name,
        first_name="Иван",
        middle_name="Иванович",
        birth_date=date(1990, 1, 1),
        **extra,
    )


def update_payload(last_name: str, **extra) -> ClientUpdate:
    return ClientUpdate(
        last_name=last_name,
        first_name="Иван",
        middle_name="Иванович",
        birth_date=date(1990, 1, 1),
        **extra,
    )


class ClientCentersTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add_all(
            [
                Center(id=1, code="center-a", name="Мед-Авто"),
                Center(id=2, code="center-b", name="Медилэнд"),
                Center(id=3, code="center-c", name="ПЕРВАЯ ЗДРАВНИЦА"),
            ]
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def create(self, last_name: str, center_ids, user=None):
        return create_client(client_payload(last_name, center_ids=center_ids), db=self.db, current_user=user)

    def list_names(self, center_ids):
        clients = list_clients(
            search=None,
            encounter_date=None,
            encounter_date_from=None,
            encounter_date_to=None,
            center_ids=center_ids,
            limit=100,
            offset=0,
            db=self.db,
        )
        return sorted(client.last_name for client in clients)

    def search_names(self, center_ids, search=None):
        rows = search_clients(
            search=search,
            encounter_date=None,
            encounter_date_from=None,
            encounter_date_to=None,
            center_ids=center_ids,
            limit=100,
            offset=0,
            db=self.db,
        )
        return sorted(row.last_name for row in rows)

    def dashboard_rows(self, center_ids):
        return get_dashboard_encounter_rows(
            search=None,
            encounter_date=None,
            encounter_date_from=None,
            encounter_date_to=None,
            center_ids=center_ids,
            limit=100,
            offset=0,
            db=self.db,
        )


class CreateClientTests(ClientCentersTestCase):
    def test_a_client_can_be_added_to_both_centers_at_once(self):
        created = self.create("Петров", [1, 2])

        self.assertEqual(created.center_ids, [1, 2])
        self.assertEqual(self.list_names([1]), ["Петров"])
        self.assertEqual(self.list_names([2]), ["Петров"])
        self.assertEqual(self.list_names([3]), [])

    def test_a_client_added_to_one_center_stays_in_that_center(self):
        created = self.create("Сидоров", [2])

        self.assertEqual(created.center_ids, [2])
        self.assertEqual(self.list_names([1]), [])
        self.assertEqual(self.list_names([2]), ["Сидоров"])

    def test_without_a_center_the_clients_go_to_the_staff_main_center(self):
        staff = SimpleNamespace(pinned_center_id=3)

        created = self.create("Кузнецов", None, user=staff)

        self.assertEqual(created.center_ids, [3])

    def test_without_a_center_and_without_a_user_the_first_working_center_is_used(self):
        created = self.create("Смирнов", None)

        self.assertEqual(created.center_ids, [1])

    def test_an_unknown_center_is_refused(self):
        with self.assertRaises(HTTPException) as caught:
            self.create("Орлов", [99])

        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(self.list_names(None), [])

    def test_a_namesake_from_another_center_is_not_a_duplicate(self):
        self.create("Иванов", [1])

        namesake = self.create("Иванов", [2])

        self.assertEqual(namesake.center_ids, [2])
        self.assertEqual(self.list_names([1]), ["Иванов"])
        self.assertEqual(self.list_names([2]), ["Иванов"])

    def test_a_namesake_in_the_same_center_is_still_a_duplicate(self):
        self.create("Иванов", [1])

        with self.assertRaises(HTTPException) as caught:
            self.create("Иванов", [1, 2])

        self.assertEqual(caught.exception.status_code, 409)


class ListScopeTests(ClientCentersTestCase):
    def setUp(self):
        super().setUp()
        self.first = self.create("Первый", [1])
        self.second = self.create("Второй", [2])
        self.both = self.create("Общий", [1, 2])

    def test_every_list_shows_only_the_clients_of_the_asked_centers(self):
        for lister in (self.list_names, self.search_names):
            with self.subTest(lister=lister.__name__):
                self.assertEqual(lister([1]), ["Общий", "Первый"])
                self.assertEqual(lister([2]), ["Второй", "Общий"])
                self.assertEqual(lister([1, 2]), ["Второй", "Общий", "Первый"])

    def test_without_centers_the_list_is_not_narrowed(self):
        self.assertEqual(self.list_names(None), ["Второй", "Общий", "Первый"])

    def test_search_stays_inside_the_asked_centers(self):
        self.assertEqual(self.search_names([2], search="Первый"), [])
        self.assertEqual(self.search_names([1], search="Первый"), ["Первый"])

    def test_deleted_clients_are_listed_per_center_too(self):
        self.db.get(Client, self.first.id).deleted_at = date(2026, 10, 1)
        self.db.get(Client, self.second.id).deleted_at = date(2026, 10, 1)
        self.db.commit()

        first_center = list_deleted_clients(search=None, center_ids=[1], limit=100, db=self.db)
        second_center = list_deleted_clients(search=None, center_ids=[2], limit=100, db=self.db)

        self.assertEqual([item.id for item in first_center], [self.first.id])
        self.assertEqual([item.id for item in second_center], [self.second.id])


class UpdateClientCentersTests(ClientCentersTestCase):
    def test_centers_are_replaced_by_the_new_list(self):
        created = self.create("Петров", [1])

        updated = update_client(created.id, update_payload("Петров", center_ids=[1, 2]), db=self.db)

        self.assertEqual(updated.center_ids, [1, 2])
        self.assertEqual(self.list_names([2]), ["Петров"])

    def test_an_edit_without_centers_leaves_them_alone(self):
        created = self.create("Петров", [1, 3])

        updated = update_client(created.id, update_payload("Петров", phone="+7 900 000-00-00"), db=self.db)

        self.assertEqual(updated.center_ids, [1, 3])
        self.assertEqual(updated.phone, "+7 900 000-00-00")

    def test_a_client_cannot_be_left_without_a_center(self):
        created = self.create("Петров", [1])

        with self.assertRaises(HTTPException) as caught:
            update_client(created.id, update_payload("Петров", center_ids=[]), db=self.db)

        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(self.db.get(Client, created.id).center_ids, [1])

    def test_moving_into_a_center_with_a_namesake_is_refused(self):
        self.create("Иванов", [2])
        created = self.create("Иванов", [1])

        with self.assertRaises(HTTPException) as caught:
            update_client(created.id, update_payload("Иванов", center_ids=[2]), db=self.db)

        self.assertEqual(caught.exception.status_code, 409)

    def test_an_ordinary_edit_ignores_a_namesake_in_another_center(self):
        self.create("Иванов", [2])
        created = self.create("Иванов", [1])

        updated = update_client(created.id, update_payload("Иванов", phone="+7 900 111-11-11"), db=self.db)

        self.assertEqual(updated.phone, "+7 900 111-11-11")


class DashboardJournalTests(ClientCentersTestCase):
    def add_encounter(self, client_id: int, center_id: int, day: int) -> None:
        self.db.add(
            Encounter(
                center_id=center_id,
                client_id=client_id,
                encounter_date=date(2026, 10, day),
                payment_type="cash",
                status="draft",
            )
        )
        self.db.commit()

    def test_the_journal_shows_only_the_clients_and_encounters_of_the_asked_centers(self):
        first = self.create("Первый", [1])
        second = self.create("Второй", [2])
        both = self.create("Общий", [1, 2])
        self.add_encounter(first.id, 1, 1)
        self.add_encounter(second.id, 2, 2)
        self.add_encounter(both.id, 1, 3)
        self.add_encounter(both.id, 2, 4)

        rows_first = self.dashboard_rows([1])
        rows_second = self.dashboard_rows([2])
        rows_both = self.dashboard_rows([1, 2])

        self.assertEqual(sorted((row.last_name, row.center_id) for row in rows_first), [("Общий", 1), ("Первый", 1)])
        self.assertEqual(sorted((row.last_name, row.center_id) for row in rows_second), [("Второй", 2), ("Общий", 2)])
        self.assertEqual(len(rows_both), 4)
        self.assertEqual(len(self.dashboard_rows(None)), 4)

    def test_a_client_with_encounters_only_in_another_center_stays_as_an_empty_row(self):
        both = self.create("Общий", [1, 2])
        self.add_encounter(both.id, 2, 4)

        rows = self.dashboard_rows([1])

        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].encounter_id)
        self.assertEqual(rows[0].client_center_ids, [1, 2])

    def test_rows_carry_the_centers_of_the_client(self):
        both = self.create("Общий", [1, 2])
        self.add_encounter(both.id, 1, 3)

        rows = self.dashboard_rows(None)

        self.assertEqual(rows[0].client_center_ids, [1, 2])


class EncounterJoinsCenterTests(ClientCentersTestCase):
    def test_an_encounter_makes_the_client_a_client_of_its_center(self):
        created = self.create("Петров", [1])

        create_encounter(
            EncounterCreate(center_id=2, client_id=created.id, encounter_date=date(2026, 10, 7), payment_type="cash"),
            db=self.db,
        )

        self.assertEqual(self.db.get(Client, created.id).center_ids, [1, 2])
        self.assertEqual(self.list_names([2]), ["Петров"])

    def test_an_encounter_in_the_own_center_changes_nothing(self):
        created = self.create("Петров", [1])

        create_encounter(
            EncounterCreate(center_id=1, client_id=created.id, encounter_date=date(2026, 10, 7), payment_type="cash"),
            db=self.db,
        )

        self.assertEqual(self.db.get(Client, created.id).center_ids, [1])


class ImportMatchesInsideTheCenterTests(ClientCentersTestCase):
    """Загрузка файла одного центра не перезаписывает карточки другого."""

    ROW = {
        "patient_number": None,
        "last_name": "Ivanov",
        "first_name": "Ivan",
        "middle_name": "Ivanovich",
        "birth_date": date(1990, 1, 1),
        "snils": None,
        "document_series": None,
        "document_number": None,
    }

    def create_ascii(self, last_name: str, center_ids):
        # SQLite не приводит кириллицу к нижнему регистру, поэтому сравнение по ФИО
        # проверяем на латинице.
        return create_client(
            ClientCreate(
                last_name=last_name,
                first_name="Ivan",
                middle_name="Ivanovich",
                birth_date=date(1990, 1, 1),
                center_ids=center_ids,
            ),
            db=self.db,
            current_user=None,
        )

    def test_a_person_from_another_center_is_not_matched(self):
        created = self.create_ascii("Ivanov", [1])

        found_here, _ = find_existing_client_for_import(self.db, self.ROW, center_id=1)
        found_elsewhere, _ = find_existing_client_for_import(self.db, self.ROW, center_id=2)

        self.assertEqual(found_here.id, created.id)
        self.assertIsNone(found_elsewhere)

    def test_without_a_center_the_whole_base_is_searched(self):
        created = self.create_ascii("Ivanov", [1])

        found, _ = find_existing_client_for_import(self.db, self.ROW)

        self.assertEqual(found.id, created.id)

    def test_the_patient_number_stays_unique_across_centers(self):
        created = self.create_ascii("Ivanov", [1])

        found, reason = find_existing_client_for_import(
            self.db, {**self.ROW, "last_name": "Other", "patient_number": created.patient_number}, center_id=2
        )

        self.assertEqual(found.id, created.id)
        self.assertEqual(reason, "по № пациента")


class MigrationBackfillTests(unittest.TestCase):
    """Уже заведённые клиенты остаются там, где с ними работали."""

    def load_migration(self):
        spec = importlib.util.spec_from_file_location("client_centers_migration", MIGRATION_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_existing_clients_are_placed_by_their_encounters_or_in_the_first_center(self):
        engine = create_engine("sqlite:///:memory:")
        tables = [table for name, table in Base.metadata.tables.items() if name != "client_centers"]
        Base.metadata.create_all(engine, tables=tables)
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO centers (id, code, name, is_active, created_at, updated_at) VALUES "
                                    "(1, 'center-a', 'Мед-Авто', 1, '2026-01-01', '2026-01-01'), "
                                    "(2, 'center-b', 'Медилэнд', 1, '2026-01-01', '2026-01-01')"))
            for client_id in (1, 2, 3, 4):
                connection.execute(
                    text(
                        "INSERT INTO clients (id, patient_number, last_name, first_name, birth_date, created_at, updated_at) "
                        "VALUES (:id, :id, 'Клиент', 'Тест', '1990-01-01', '2026-01-01', '2026-01-01')"
                    ),
                    {"id": client_id},
                )
            encounters = [
                (1, 1, 2, None),   # клиент 1: обращение в Медилэнде
                (2, 2, 1, None),   # клиент 2: обращения в обоих центрах
                (3, 2, 2, None),
                (4, 3, 2, "2026-02-01"),  # клиент 3: единственное обращение удалено
            ]
            for encounter_id, client_id, center_id, deleted_at in encounters:
                connection.execute(
                    text(
                        "INSERT INTO encounters (id, center_id, client_id, encounter_date, payment_type, status, "
                        "total_amount, suppressed_doctor_role_ids, deleted_at, created_at, updated_at) "
                        "VALUES (:id, :center, :client, '2026-02-01', 'cash', 'draft', 0, '[]', :deleted, "
                        "'2026-02-01', '2026-02-01')"
                    ),
                    {"id": encounter_id, "center": center_id, "client": client_id, "deleted": deleted_at},
                )

            migration = self.load_migration()
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()

            self.assertTrue(inspect(connection).has_table("client_centers"))
            rows = connection.execute(
                select(client_centers.c.client_id, client_centers.c.center_id).order_by(
                    client_centers.c.client_id, client_centers.c.center_id
                )
            ).all()

        # Клиент 3 (обращение удалено) и клиент 4 (обращений нет) — в первом центре.
        self.assertEqual(
            [tuple(row) for row in rows],
            [(1, 2), (2, 1), (2, 2), (3, 1), (4, 1)],
        )
        engine.dispose()

    def test_a_fresh_database_that_already_has_the_table_is_left_alone(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            migration = self.load_migration()
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            self.assertEqual(connection.execute(select(client_centers.c.client_id)).all(), [])
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
