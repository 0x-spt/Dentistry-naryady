"""Бизнес-проверки: можно ли пустить наряд в таблицу без человека.

Возвращают список проблем. Пустой список = «ок», иначе — «на проверку».
"""

import re

from naryad.clients import Clients
from naryad.schema import Naryad
from naryad.text import norm_text

VITA = re.compile(r"^[ABCD][1-4](\.5)?$")  # классическая шкала VITA: A1…D4, плюс A3.5/B3.5…
REQUIRED = ("number", "issued", "clinic", "patient", "due_date")


def valid_tooth(t: int) -> bool:
    """FDI: первая цифра — четверть 1–4, вторая — зуб 1–8."""
    return 1 <= t // 10 <= 4 and 1 <= t % 10 <= 8


def check(n: Naryad, clients: Clients) -> list[str]:
    problems = []

    for field in REQUIRED:
        if getattr(n, field) is None:
            problems.append(f"нет обязательного поля {field}")

    bad = [t for t in n.teeth if not valid_tooth(t)]
    if bad:
        problems.append(f"несуществующие зубы {bad}")

    if n.shade and not VITA.match(n.shade):
        problems.append(f"цвет {n.shade!r} не по шкале VITA")

    # Сумму считаем, только если у всех строк есть и количество, и цена — иначе сравнивать не с чем
    if n.total is not None and n.works and all(w.qty is not None and w.unit_price is not None for w in n.works):
        calc = sum(w.qty * w.unit_price for w in n.works)
        if calc != n.total:
            problems.append(f"итого {n.total} ≠ сумма строк {calc}")

    if n.issued and n.due_date and n.due_date < n.issued:
        problems.append("сдача раньше даты наряда")
    if n.fitting_date and n.due_date and n.fitting_date > n.due_date:
        problems.append("примерка позже сдачи")

    # Справочник: сравниваем без учёта пробелов, точек и регистра
    known = {norm_text(c): [norm_text(d) for d in docs] for c, docs in clients.items()}
    if n.clinic and norm_text(n.clinic) not in known:
        problems.append(f"клиники {n.clinic!r} нет в справочнике")
    elif n.clinic and n.doctor and norm_text(n.doctor) not in known[norm_text(n.clinic)]:
        problems.append(f"врач {n.doctor!r} не работает в {n.clinic!r} по справочнику")

    if n.unreadable:
        problems.append(f"модель не уверена в полях {n.unreadable}")

    return problems
