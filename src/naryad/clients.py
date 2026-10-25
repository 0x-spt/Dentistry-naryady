"""Справочник клиентов лаборатории: клиники и их врачи.

У лаборатории конечный список клиентов — в проде его выгружают из CRM.
Справочник работает дважды: подсказывает модели, как пишутся фамилии
(«Шахов» прописью → «Иванов»), и ловит в checks.py то, чего в нём нет.
"""

import json
from pathlib import Path

Clients = dict[str, list[str]]  # {клиника: [врачи]}


def load_clients(path: Path) -> Clients:
    return json.loads(path.read_text(encoding="utf-8"))
