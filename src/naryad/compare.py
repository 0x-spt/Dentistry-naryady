"""Сравнение ответа модели с эталоном по полям."""

from naryad.schema import Naryad
from naryad.text import norm_shade, norm_text

# Поля, которые оцениваем автоматически. name работ и note — свободный текст,
# их сравнение «на равенство» врало бы; смотрим глазами в отчёте.
GRADED = (
    "number", "issued", "clinic", "doctor", "patient", "technician",
    "teeth", "shade", "total", "fitting_date", "due_date", "works",
)
TEXT_FIELDS = {"number", "clinic", "doctor", "patient", "technician"}


def works_key(n: Naryad) -> list[tuple]:
    """Работы сравниваем по количеству и цене — это то, что идёт в деньги."""
    return sorted((w.qty, w.unit_price) for w in n.works)


def compare(got: Naryad, truth: Naryad) -> dict[str, bool]:
    """{поле: совпало ли}."""
    result = {}
    for f in GRADED:
        g, t = getattr(got, f), getattr(truth, f)
        if f in TEXT_FIELDS:
            ok = norm_text(g) == norm_text(t)
        elif f == "shade":
            ok = norm_shade(g) == norm_shade(t)
        elif f == "teeth":
            ok = sorted(g) == sorted(t)  # порядок зубов не важен
        elif f == "works":
            ok = works_key(got) == works_key(truth)
        else:
            ok = g == t
        result[f] = ok
    return result
