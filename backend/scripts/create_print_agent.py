"""Выдать токен печатному агенту рабочего места, показать список агентов или отозвать агент.

Запуск из папки backend (строка подключения берется из окружения или .env):

    python scripts/create_print_agent.py --name "Регистратура, ПК 1" --center center-a --printer "HP LaserJet"
    python scripts/create_print_agent.py --list
    python scripts/create_print_agent.py --revoke 3

Токен печатается один раз и в базе не хранится: там только его sha256.
Без --center агент печатает задания всех центров.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

import app.models  # noqa: E402,F401
from app.db.session import SessionLocal  # noqa: E402
from app.models.center import Center  # noqa: E402
from app.models.print_queue import PrintAgent  # noqa: E402
from app.services.print_queue import (  # noqa: E402
    PrintQueueError,
    agent_is_online,
    create_agent,
    revoke_agent,
    utc_now,
)


def _resolve_center_id(db, center: str) -> int:
    if center.isdigit():
        found = db.get(Center, int(center))
    else:
        found = db.execute(select(Center).where(Center.code == center)).scalar_one_or_none()
    if found is None:
        raise SystemExit(f"Центр «{center}» не найден. Коды центров: center-a, center-b, center-c.")
    return found.id


def _print_list(db) -> None:
    agents = db.execute(select(PrintAgent).order_by(PrintAgent.id)).scalars().all()
    if not agents:
        print("Печатных агентов пока нет.")
        return
    now = utc_now()
    for agent in agents:
        if agent.revoked_at is not None:
            state = "отозван"
        elif agent_is_online(agent, now):
            state = "в сети"
        else:
            state = "не в сети"
        center = agent.center_id if agent.center_id is not None else "все центры"
        print(f"{agent.id}\t{state}\tцентр: {center}\tпринтер: {agent.printer_name or 'по умолчанию'}\t{agent.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Печатные агенты рабочих мест Vova Medcenter")
    parser.add_argument("--name", help="название рабочего места, например «Регистратура, ПК 1»")
    parser.add_argument("--center", help="код центра (center-a, center-b, center-c) или его номер; без него — все центры")
    parser.add_argument("--printer", default="", help="принтер агента; пусто — принтер по умолчанию на ПК")
    parser.add_argument("--list", action="store_true", help="показать агенты и их состояние")
    parser.add_argument("--revoke", type=int, metavar="ID", help="отозвать агент по номеру из --list")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.list:
            _print_list(db)
            return 0
        if args.revoke is not None:
            try:
                agent = revoke_agent(db, args.revoke)
            except PrintQueueError as exc:
                print(exc.detail)
                return 1
            print(f"Агент «{agent.name}» отозван. Его задания больше не забираются.")
            return 0
        if not args.name:
            parser.error("укажите --name, либо --list, либо --revoke")
        center_id = _resolve_center_id(db, args.center) if args.center else None
        agent, token = create_agent(db, name=args.name, center_id=center_id, printer_name=args.printer)
        print(f"Агент «{agent.name}» создан, номер {agent.id}.")
        print("Токен (покажется один раз, сохраните его в print_agent/agent.json):")
        print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
