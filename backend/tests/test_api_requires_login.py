"""Без токена работают только вход, проверка здоровья, ссылки печати и маршруты печатного агента.

Тест проходит по всем маршрутам API и требует get_current_user в дереве зависимостей
каждого маршрута, кроме разрешенных. Новый открытый маршрут сначала нужно внести в список.
Маршруты печатного агента открыты для входа сотрудника, но требуют токен агента
(X-Print-Agent-Token): их проверяет test_print_queue.py.
"""

from pathlib import Path
import sys
import unittest

from fastapi.routing import APIRoute


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401
from app.api.router import api_router  # noqa: E402
from app.api.v1.routes.auth import get_current_user  # noqa: E402


PUBLIC_PATHS = {
    "/auth/login",
    "/health",
    "/documents/print-ticket/{token}",
    "/documents/print-ticket/{token}/{file_name}",
    "/print-agent/heartbeat",
    "/print-agent/jobs/claim",
    "/print-agent/jobs/{job_id}/result",
}


def _dependency_calls(dependant) -> set:
    calls = set()
    for child in dependant.dependencies:
        calls.add(child.call)
        calls |= _dependency_calls(child)
    return calls


class ApiRequiresLoginTests(unittest.TestCase):
    def test_only_login_health_and_print_tickets_are_open(self):
        routes = [route for route in api_router.routes if isinstance(route, APIRoute)]
        self.assertGreater(len(routes), 50)
        open_paths = {
            route.path for route in routes if get_current_user not in _dependency_calls(route.dependant)
        }
        self.assertEqual(open_paths, PUBLIC_PATHS)


if __name__ == "__main__":
    unittest.main()
