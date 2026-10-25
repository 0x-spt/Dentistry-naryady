"""Запись в таблицу без Google: FakeSheet (conftest) хранит строки в памяти."""

from datetime import datetime

import pytest
from conftest import FakeSheet, make

from naryad.schema import WorkItem
from naryad.sheets import CHECKED, NARYAD_HEADER, REVIEW, STATUS_COL, WORK_HEADER, write

NOW = datetime(2026, 10, 24, 12, 0)


def put(n, problems=(), photo="naryad_01.jpg", sheets=None):
    naryady, raboty = sheets or (FakeSheet(), FakeSheet())
    action, _ = write(naryady, raboty, n, list(problems), photo, "claude-opus-5-5", NOW)
    return action, naryady, raboty


def test_first_write_adds_header_and_rows():
    action, naryady, raboty = put(make(number="101"))
    assert action == "добавлен"
    assert naryady.rows[0] == NARYAD_HEADER and raboty.rows[0] == WORK_HEADER
    row = dict(zip(NARYAD_HEADER, naryady.rows[1], strict=True))
    assert row["Ключ"] == "№101" and row["Статус"] == "ОК" and row["Сдача"] == "2026-10-28"
    assert raboty.rows[1] == ["№101", "101", "коронка", "", 2, 9000, 18000]


def test_same_naryad_again_updates_not_duplicates():
    _, naryady, raboty = put(make(number="101"))
    two_works = [WorkItem(name="коронка", material=None, qty=1, unit_price=9000),
                 WorkItem(name="винир", material="E.max", qty=1, unit_price=9000)]
    action, naryady, raboty = put(make(number="101", works=two_works), ["итого не сходится"],
                                  sheets=(naryady, raboty))
    assert action == "обновлён"
    assert len(naryady.rows) == 2
    assert naryady.rows[1][STATUS_COL] == REVIEW
    assert [r[2] for r in raboty.rows[1:]] == ["коронка", "винир"]  # старая строка работ заменена


def test_checked_by_human_is_not_overwritten():
    _, naryady, raboty = put(make(number="101", patient="Сидорова"))
    naryady.rows[1][STATUS_COL] = CHECKED
    action, naryady, _ = put(make(number="101", patient="Сидоров"), sheets=(naryady, raboty))
    assert action == "пропущен"
    assert "Сидорова" in naryady.rows[1]


def test_no_number_keyed_by_photo():
    _, naryady, _ = put(make(number=None), ["нет обязательного поля number"], photo="IMG_7.jpg")
    assert naryady.rows[1][0] == "фото:IMG_7.jpg"


def test_works_of_other_naryady_untouched():
    _, naryady, raboty = put(make(number="101"))
    put(make(number="102"), sheets=(naryady, raboty))
    put(make(number="101"), sheets=(naryady, raboty))
    assert sorted(r[0] for r in raboty.rows[1:]) == ["№101", "№102"]


def test_foreign_header_refused():
    with pytest.raises(ValueError, match="другая шапка"):
        put(make(), sheets=(FakeSheet([["Что-то своё"]]), FakeSheet()))


def test_same_number_from_other_photo_is_not_overwritten():
    _, naryady, raboty = put(make(number="101", patient="Сидорова"), photo="naryad_01.jpg")
    action, naryady, raboty = put(make(number="101", patient="Петров"), photo="naryad_09.jpg",
                                  sheets=(naryady, raboty))
    assert action == "добавлен"
    assert [r[0] for r in naryady.rows[1:]] == ["№101", "№101 / naryad_09.jpg"]
    assert "Сидорова" in naryady.rows[1]
    assert naryady.rows[2][STATUS_COL] == REVIEW and "номер уже есть" in naryady.rows[2][STATUS_COL + 1]
    # повторная отправка того же второго фото обновляет его строку, а не плодит третью
    action, naryady, _ = put(make(number="101"), photo="naryad_09.jpg", sheets=(naryady, raboty))
    assert action == "обновлён" and len(naryady.rows) == 3
