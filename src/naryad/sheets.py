"""Запись распознанных нарядов в Google Таблицу.

Два листа:
- «Наряды» — строка на наряд: поля, статус, причины проверки;
- «Работы» — строка на работу, связана с нарядом по ключу.

Запись идемпотентна: ключ — номер наряда (или имя фото, если номер не распознан).
Повторная отправка того же фото обновляет строку, а не дублирует её. Тот же номер с другого
фото пишется отдельной строкой «на проверку» — молча перезаписывать чужой наряд нельзя.
Строку, которую человек отметил «проверено», не перезаписываем — его правки важнее модели.

Логика работает с любым объектом, похожим на gspread.Worksheet (см. Sheet),
поэтому в тестах вместо Google подставляется список в памяти.
"""

import logging
from datetime import datetime
from typing import Any, Protocol

from naryad.schema import Naryad

log = logging.getLogger(__name__)

NARYADY, RABOTY = "Наряды", "Работы"
NARYAD_HEADER = [
    "Ключ", "Номер", "Дата", "Клиника", "Врач", "Пациент", "Техник", "Зубы", "Цвет", "Итого",
    "Примерка", "Сдача", "Примечание", "Статус", "Причины", "Фото", "Модель", "Распознано",
]
WORK_HEADER = ["Ключ", "Номер", "Работа", "Материал", "Кол-во", "Цена", "Сумма"]
STATUS_COL = NARYAD_HEADER.index("Статус")
PHOTO_COL = NARYAD_HEADER.index("Фото")

OK, REVIEW, CHECKED = "ОК", "На проверку", "Проверено"  # «Проверено» ставит человек


class Sheet(Protocol):
    """Подмножество gspread.Worksheet, которое нам нужно."""

    def get_all_values(self) -> list[list[str]]: ...
    def update(self, values: list[list[Any]], range_name: str, value_input_option: str) -> Any: ...
    def append_rows(self, values: list[list[Any]], value_input_option: str) -> Any: ...
    def delete_rows(self, start_index: int, end_index: int | None = None) -> Any: ...


def key_of(n: Naryad, photo_name: str) -> str:
    return f"№{n.number}" if n.number else f"фото:{photo_name}"


def _d(value) -> str:
    return value.isoformat() if value else ""


def naryad_row(n: Naryad, key: str, problems: list[str], photo_name: str, model: str, now: datetime) -> list[Any]:
    return [
        key, n.number or "", _d(n.issued), n.clinic or "", n.doctor or "", n.patient or "",
        n.technician or "", ", ".join(map(str, n.teeth)), n.shade or "", n.total if n.total is not None else "",
        _d(n.fitting_date), _d(n.due_date), n.note or "", REVIEW if problems else OK, "; ".join(problems),
        photo_name, model, now.strftime("%Y-%m-%d %H:%M"),
    ]


def work_rows(n: Naryad, key: str) -> list[list[Any]]:
    rows = []
    for w in n.works:
        line_sum = w.qty * w.unit_price if w.qty is not None and w.unit_price is not None else ""
        rows.append([key, n.number or "", w.name, w.material or "",
                     w.qty if w.qty is not None else "", w.unit_price if w.unit_price is not None else "", line_sum])
    return rows


def ensure_header(ws: Sheet, header: list[str]) -> list[list[str]]:
    """Возвращает все строки листа; на пустом листе сначала пишет шапку."""
    values = ws.get_all_values()
    if not values or not any(values[0]):
        ws.update([header], range_name="A1", value_input_option="RAW")
        return [header]
    if values[0][: len(header)] != header:
        raise ValueError(f"на листе другая шапка: {values[0]!r} — таблица не та или её меняли руками")
    return values


def write(naryady: Sheet, raboty: Sheet, n: Naryad, problems: list[str], photo_name: str, model: str,
          now: datetime | None = None) -> tuple[str, list[str]]:
    """Записывает наряд. Возвращает, что сделано («добавлен», «обновлён», «пропущен»),
    и итоговые причины проверки — к проблемам проверок может добавиться дубль номера."""
    now = now or datetime.now()
    key = key_of(n, photo_name)
    rows = ensure_header(naryady, NARYAD_HEADER)

    def find(k: str) -> int | None:
        return next((i for i, r in enumerate(rows) if i > 0 and r and r[0] == k), None)

    existing = find(key)
    # Тот же номер с другого фото — это не повторная отправка, а другой наряд или ошибка чтения номера.
    # Перезаписать = молча потерять первый наряд, поэтому пишем отдельной строкой и отдаём человеку.
    if existing is not None and rows[existing][PHOTO_COL] != photo_name:
        problems = [*problems, f"номер уже есть в таблице (фото {rows[existing][PHOTO_COL]})"]
        key = f"{key} / {photo_name}"
        existing = find(key)

    if existing is not None and len(rows[existing]) > STATUS_COL and rows[existing][STATUS_COL] == CHECKED:
        log.warning("%s уже проверен человеком — не перезаписываю", key)
        return "пропущен", problems

    row = naryad_row(n, key, problems, photo_name, model, now)
    if existing is None:
        naryady.append_rows([row], value_input_option="USER_ENTERED")
        action = "добавлен"
    else:
        naryady.update([row], range_name=f"A{existing + 1}", value_input_option="USER_ENTERED")
        action = "обновлён"

    # Работы: старые строки этого наряда удаляем (снизу вверх, чтобы не сбить номера) и пишем заново
    work_values = ensure_header(raboty, WORK_HEADER)
    for i in reversed([i for i, r in enumerate(work_values) if i > 0 and r and r[0] == key]):
        raboty.delete_rows(i + 1)
    if n.works:
        raboty.append_rows(work_rows(n, key), value_input_option="USER_ENTERED")
    return action, problems


def open_sheets(credentials_file: str, spreadsheet_id: str) -> tuple[Sheet, Sheet]:
    """Открывает оба листа, создавая недостающие. Импорт gspread здесь — тестам он не нужен."""
    import gspread

    book = gspread.service_account(filename=credentials_file).open_by_key(spreadsheet_id)
    sheets = []
    for title, header in ((NARYADY, NARYAD_HEADER), (RABOTY, WORK_HEADER)):
        try:
            sheets.append(book.worksheet(title))
        except gspread.WorksheetNotFound:
            sheets.append(book.add_worksheet(title, rows=1000, cols=len(header)))
    return sheets[0], sheets[1]
