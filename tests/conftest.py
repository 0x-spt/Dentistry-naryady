from datetime import date
from pathlib import Path

import pytest

from naryad.clients import load_clients
from naryad.schema import Naryad, WorkItem

DATA = Path(__file__).parent.parent / "data"
TRUTH_FILES = sorted((DATA / "truth").glob("*.json"))


@pytest.fixture
def clients():
    return load_clients(DATA / "clients.json")


def make(**over) -> Naryad:
    """Корректный наряд; в тесте меняем только то, что проверяем."""
    base = dict(
        number="1", issued=date(2026, 10, 20), clinic="Улыбка+", doctor="Петрова А.В.", patient="П",
        technician="Т", teeth=[11], works=[WorkItem(name="коронка", material=None, qty=2, unit_price=9000)],
        shade="A2", total=18000, fitting_date=date(2026, 10, 24), due_date=date(2026, 10, 28),
        note=None, unreadable=[],
    )
    return Naryad(**(base | over))


# Лист Google Таблицы в памяти: ведёт себя как gspread.Worksheet в тех методах, что нам нужны.#
class FakeSheet:
    def __init__(self, rows: list[list] | None = None):
        self.rows = rows or []

    def get_all_values(self):
        return [[str(c) for c in r] for r in self.rows]

    def update(self, values, range_name, value_input_option):
        i = int(range_name[1:]) - 1  # «A5» → строка 4
        while len(self.rows) <= i:
            self.rows.append([])
        self.rows[i] = list(values[0])

    def append_rows(self, values, value_input_option):
        self.rows.extend(list(v) for v in values)

    def delete_rows(self, start_index, end_index=None):
        del self.rows[start_index - 1 : (end_index or start_index)]
