"""Очередь тихой печати: кто ставит задание, кто его забирает и как он заканчивается.

Проверяем, что: задание ставится только когда агент центра в сети; сотрудник другого центра
не ставит и не отменяет чужие документы; агент получает задание своего центра ровно один раз;
файл отдается по временной ссылке; повторный отчет ничего не меняет; взятое задание нельзя отменить;
зависшее задание помечается ошибкой, а не печатается повторно.
"""

from datetime import date, timedelta
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.v1.routes import print_queue as routes  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.document_template import DocumentTemplate  # noqa: E402
from app.models.encounter import Encounter  # noqa: E402
from app.models.generated_document import GeneratedDocument  # noqa: E402
from app.models.print_queue import (  # noqa: E402
    PRINT_JOB_CANCELLED,
    PRINT_JOB_CLAIMED,
    PRINT_JOB_DONE,
    PRINT_JOB_FAILED,
    PRINT_JOB_QUEUED,
    PrintJob,
)
from app.models.user import Role, User  # noqa: E402
from app.schemas.print_queue import AgentResultRequest, PrintJobCreate  # noqa: E402
from app.services import print_queue as service  # noqa: E402


class DummyRequest:
    """Минимальный Request: для выдачи ссылки нужны url_for и заголовок host."""

    def __init__(self, host: str = "localhost:8000") -> None:
        self.headers = {"host": host}

    def url_for(self, route_name, **path_params):
        return f"http://localhost:8000/api/v1/documents/print-ticket/{path_params['token']}/{path_params['file_name']}"


class PrintQueueTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.tmp = tempfile.TemporaryDirectory()
        self.file_path = Path(self.tmp.name) / "a.docx"
        self.file_path.write_bytes(b"docx")
        with self.Session() as db:
            admin_role = Role(code="admin", name="Администратор")
            operator_role = Role(code="operator", name="Оператор")
            db.add_all([admin_role, operator_role])
            db.flush()
            center_a = Center(code="center-a", name="Медцентр 1")
            center_b = Center(code="center-b", name="Медцентр 2")
            db.add_all([center_a, center_b])
            db.flush()
            db.add_all(
                [
                    User(role_id=admin_role.id, login="admin", password_hash=hash_password("x"), full_name="Админ", center_id=center_a.id),
                    User(role_id=operator_role.id, login="op_a", password_hash=hash_password("x"), full_name="Оператор A", center_id=center_a.id),
                    User(role_id=operator_role.id, login="op_b", password_hash=hash_password("x"), full_name="Оператор B", center_id=center_b.id),
                ]
            )
            client = Client(patient_number=1, last_name="Иванов", first_name="Иван", birth_date=date(1990, 1, 1))
            template = DocumentTemplate(code="ref", name="Справка", file_name="ref.docx")
            db.add_all([client, template])
            db.flush()
            encounter_a = Encounter(center_id=center_a.id, client_id=client.id, encounter_date=date(2026, 11, 19), payment_type="cash")
            encounter_b = Encounter(center_id=center_b.id, client_id=client.id, encounter_date=date(2026, 11, 19), payment_type="cash")
            db.add_all([encounter_a, encounter_b])
            db.flush()
            db.add_all(
                [
                    GeneratedDocument(encounter_id=encounter_a.id, client_id=client.id, template_id=template.id, file_name="a.docx", file_path="a.docx"),
                    GeneratedDocument(encounter_id=encounter_b.id, client_id=client.id, template_id=template.id, file_name="b.docx", file_path="b.docx"),
                    GeneratedDocument(encounter_id=None, client_id=client.id, template_id=template.id, file_name="free.docx", file_path="free.docx"),
                ]
            )
            db.commit()
            self.center_a_id = center_a.id
            self.center_b_id = center_b.id

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        self.tmp.cleanup()

    def _user(self, db, login: str) -> User:
        return db.execute(select(User).where(User.login == login)).scalar_one()

    def _agent(self, db, center_id, name="ПК 1"):
        agent, token = service.create_agent(db, name=name, center_id=center_id, printer_name="HP LaserJet")
        return agent, token

    def _bring_online(self, db, agent) -> None:
        service.touch_agent(db, agent, service.utc_now())

    def _create_job(self, db, user_login: str, file_name: str):
        user = self._user(db, user_login)
        return routes.create_print_job(PrintJobCreate(file_name=file_name), db=db, current_user=user)

    def test_job_is_queued_when_agent_of_the_center_is_online(self):
        with self.Session() as db:
            agent, _ = self._agent(db, self.center_a_id)
            self._bring_online(db, agent)
            job = self._create_job(db, "op_a", "a.docx")
        self.assertEqual(job.status, PRINT_JOB_QUEUED)
        self.assertEqual(job.copies, 1)

    def test_no_online_agent_means_no_job_and_409(self):
        with self.Session() as db:
            self._agent(db, self.center_a_id)  # агент есть, но ни разу не выходил на связь
            with self.assertRaises(HTTPException) as ctx:
                self._create_job(db, "op_a", "a.docx")
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertEqual(db.execute(select(PrintJob)).scalars().all(), [])

    def test_agent_of_other_center_does_not_count(self):
        with self.Session() as db:
            agent, _ = self._agent(db, self.center_b_id)
            self._bring_online(db, agent)
            with self.assertRaises(HTTPException) as ctx:
                self._create_job(db, "op_a", "a.docx")
            self.assertEqual(ctx.exception.status_code, 409)

    def test_stale_agent_is_not_online(self):
        with self.Session() as db:
            agent, _ = self._agent(db, self.center_a_id)
            agent.last_seen_at = service.utc_now() - timedelta(minutes=5)
            db.commit()
            self.assertFalse(service.agent_is_online(agent, service.utc_now()))

    def test_operator_cannot_print_document_of_other_center(self):
        with self.Session() as db:
            agent, _ = self._agent(db, self.center_a_id)
            self._bring_online(db, agent)
            with self.assertRaises(HTTPException) as ctx:
                self._create_job(db, "op_b", "a.docx")
            self.assertEqual(ctx.exception.status_code, 403)

    def test_admin_can_print_any_center(self):
        with self.Session() as db:
            agent, _ = self._agent(db, self.center_a_id)
            self._bring_online(db, agent)
            job = self._create_job(db, "admin", "a.docx")
        self.assertEqual(job.status, PRINT_JOB_QUEUED)

    def test_unknown_or_cancelled_document_is_not_found(self):
        with self.Session() as db:
            agent, _ = self._agent(db, self.center_a_id)
            self._bring_online(db, agent)
            with self.assertRaises(HTTPException) as ctx:
                self._create_job(db, "op_a", "missing.docx")
            self.assertEqual(ctx.exception.status_code, 404)

    def test_token_is_checked_by_hash_and_revocation_blocks_it(self):
        with self.Session() as db:
            agent, token = self._agent(db, self.center_a_id)
            self.assertEqual(service.authenticate_agent(db, token).id, agent.id)
            with self.assertRaises(service.PrintQueueError) as ctx:
                service.authenticate_agent(db, "не-тот-токен")
            self.assertEqual(ctx.exception.status_code, 401)
            with self.assertRaises(HTTPException) as route_ctx:
                routes.get_print_agent(x_print_agent_token=None, db=db)
            self.assertEqual(route_ctx.exception.status_code, 401)
            service.revoke_agent(db, agent.id)
            with self.assertRaises(service.PrintQueueError):
                service.authenticate_agent(db, token)

    def test_token_is_stored_only_as_hash(self):
        with self.Session() as db:
            agent, token = self._agent(db, self.center_a_id)
            self.assertNotEqual(agent.token_hash, token)
            self.assertEqual(agent.token_hash, service.hash_agent_token(token))

    def test_claim_gives_each_job_once_and_only_for_the_center(self):
        with self.Session() as db:
            agent_a, token_a = self._agent(db, self.center_a_id)
            self._bring_online(db, agent_a)
            agent_b, _ = self._agent(db, self.center_b_id, name="ПК 2")
            self._bring_online(db, agent_b)
            self._create_job(db, "op_b", "b.docx")
            self._create_job(db, "admin", "free.docx")
            self._create_job(db, "op_a", "a.docx")
        with self.Session() as db:
            agent = service.authenticate_agent(db, token_a)
            # Задание центра B агент центра A не берет; свободное и свое — да, по порядку создания.
            first = service.claim_next_job(db, agent, service.utc_now())
            self.assertEqual(first.file_name, "free.docx")
            second = service.claim_next_job(db, agent, service.utc_now())
            self.assertEqual(second.file_name, "a.docx")
            self.assertEqual(second.status, PRINT_JOB_CLAIMED)
            self.assertIsNone(service.claim_next_job(db, agent, service.utc_now()))

    def test_claim_route_returns_file_url_and_agent_printer(self):
        with self.Session() as db:
            agent, token = self._agent(db, self.center_a_id)
            self._bring_online(db, agent)
            self._create_job(db, "op_a", "a.docx")
        with self.Session() as db:
            agent = service.authenticate_agent(db, token)
            with patch.object(routes, "_resolve_generated_file", return_value=self.file_path):
                response = routes.agent_claim_job(DummyRequest(), agent=agent, db=db)
        self.assertIsNotNone(response.job)
        self.assertEqual(response.job.file_name, "a.docx")
        self.assertEqual(response.job.printer_name, "HP LaserJet")
        self.assertIn("/api/v1/documents/print-ticket/", response.job.file_url)

    def test_missing_file_fails_the_job_instead_of_stalling_the_queue(self):
        with self.Session() as db:
            agent, token = self._agent(db, self.center_a_id)
            self._bring_online(db, agent)
            job = self._create_job(db, "op_a", "a.docx")
            job_id = job.id
        with self.Session() as db:
            agent = service.authenticate_agent(db, token)
            with patch.object(routes, "_resolve_generated_file", return_value=None):
                response = routes.agent_claim_job(DummyRequest(), agent=agent, db=db)
            self.assertIsNone(response.job)
            failed = db.get(PrintJob, job_id)
            self.assertEqual(failed.status, PRINT_JOB_FAILED)
            self.assertEqual(failed.error, "Файл документа не найден")

    def test_result_is_recorded_once_and_repeat_does_not_change_it(self):
        with self.Session() as db:
            agent, token = self._agent(db, self.center_a_id)
            self._bring_online(db, agent)
            job_id = self._create_job(db, "op_a", "a.docx").id
        with self.Session() as db:
            agent = service.authenticate_agent(db, token)
            service.claim_next_job(db, agent, service.utc_now())
            done = routes.agent_report_result(job_id, AgentResultRequest(ok=True), agent=agent, db=db)
            self.assertEqual(done.status, PRINT_JOB_DONE)
            again = routes.agent_report_result(job_id, AgentResultRequest(ok=False, error="повтор"), agent=agent, db=db)
            self.assertEqual(again.status, PRINT_JOB_DONE)
            self.assertIsNone(again.error)

    def test_failed_print_keeps_the_error_for_the_employee(self):
        with self.Session() as db:
            agent, token = self._agent(db, self.center_a_id)
            self._bring_online(db, agent)
            job_id = self._create_job(db, "op_a", "a.docx").id
        with self.Session() as db:
            agent = service.authenticate_agent(db, token)
            service.claim_next_job(db, agent, service.utc_now())
            failed = routes.agent_report_result(job_id, AgentResultRequest(ok=False, error="Принтер выключен"), agent=agent, db=db)
            self.assertEqual(failed.status, PRINT_JOB_FAILED)
            self.assertEqual(failed.error, "Принтер выключен")

    def test_other_agent_cannot_report_a_job_it_did_not_claim(self):
        with self.Session() as db:
            agent, token = self._agent(db, self.center_a_id)
            self._bring_online(db, agent)
            other, other_token = self._agent(db, self.center_a_id, name="ПК 3")
            job_id = self._create_job(db, "op_a", "a.docx").id
        with self.Session() as db:
            service.claim_next_job(db, service.authenticate_agent(db, token), service.utc_now())
            other = service.authenticate_agent(db, other_token)
            with self.assertRaises(HTTPException) as ctx:
                routes.agent_report_result(job_id, AgentResultRequest(ok=True), agent=other, db=db)
            self.assertEqual(ctx.exception.status_code, 404)

    def test_queued_job_can_be_cancelled_but_claimed_one_cannot(self):
        with self.Session() as db:
            agent, token = self._agent(db, self.center_a_id)
            self._bring_online(db, agent)
            queued_id = self._create_job(db, "op_a", "a.docx").id
            claimed_id = self._create_job(db, "op_a", "free.docx").id
        with self.Session() as db:
            cancelled = routes.cancel_print_job(queued_id, db=db, current_user=self._user(db, "op_a"))
            self.assertEqual(cancelled.status, PRINT_JOB_CANCELLED)
        with self.Session() as db:
            service.claim_next_job(db, service.authenticate_agent(db, token), service.utc_now())
            with self.assertRaises(HTTPException) as ctx:
                routes.cancel_print_job(claimed_id, db=db, current_user=self._user(db, "op_a"))
            self.assertEqual(ctx.exception.status_code, 409)

    def test_employee_sees_only_own_or_own_center_jobs(self):
        with self.Session() as db:
            agent, _ = self._agent(db, self.center_a_id)
            self._bring_online(db, agent)
            job_id = self._create_job(db, "op_a", "a.docx").id
        with self.Session() as db:
            with self.assertRaises(HTTPException) as ctx:
                routes.get_print_job(job_id, db=db, current_user=self._user(db, "op_b"))
            self.assertEqual(ctx.exception.status_code, 403)
            seen = routes.get_print_job(job_id, db=db, current_user=self._user(db, "admin"))
            self.assertEqual(seen.id, job_id)

    def test_claimed_job_that_never_reports_back_fails_after_timeout(self):
        with self.Session() as db:
            agent, token = self._agent(db, self.center_a_id)
            self._bring_online(db, agent)
            job_id = self._create_job(db, "op_a", "a.docx").id
        with self.Session() as db:
            service.claim_next_job(db, service.authenticate_agent(db, token), service.utc_now())
        with self.Session() as db:
            job = db.get(PrintJob, job_id)
            job.claimed_at = service.utc_now() - service.CLAIM_TIMEOUT - timedelta(seconds=1)
            db.commit()
        with self.Session() as db:
            expired = service.get_job(db, job_id, service.utc_now())
            self.assertEqual(expired.status, PRINT_JOB_FAILED)
            self.assertEqual(expired.error, "Агент не ответил вовремя")
            # Задание не уходит повторно на печать: в очереди его больше нет.
            agent = service.authenticate_agent(db, token)
            self.assertIsNone(service.claim_next_job(db, agent, service.utc_now()))

    def test_copies_are_limited_between_1_and_20(self):
        self.assertEqual(PrintJobCreate(file_name="a.docx", copies=1).copies, 1)
        self.assertEqual(PrintJobCreate(file_name="a.docx", copies=20).copies, 20)
        for bad in (0, 21):
            with self.assertRaises(ValidationError):
                PrintJobCreate(file_name="a.docx", copies=bad)


if __name__ == "__main__":
    unittest.main()
