from datetime import date

import pytest
from conftest import TRUTH_FILES, make

from naryad.checks import check, valid_tooth
from naryad.schema import Naryad, WorkItem


def test_clean_naryad_has_no_problems(clients):
    assert check(make(), clients) == []


def test_wrong_total_is_flagged(clients):
    assert any("итого" in p for p in check(make(total=21000), clients))


def test_total_not_checked_without_prices(clients):
    works = [WorkItem(name="коронка", material=None, qty=2, unit_price=None)]
    assert check(make(works=works, total=999), clients) == []


@pytest.mark.parametrize("tooth,ok", [(11, True), (48, True), (36, True), (19, False), (50, False), (10, False)])
def test_fdi(tooth, ok):
    assert valid_tooth(tooth) is ok


def test_bad_shade_and_dates(clients):
    problems = check(make(shade="X9", due_date=date(2026, 10, 1), fitting_date=None), clients)
    assert any("VITA" in p for p in problems)
    assert any("сдача раньше" in p for p in problems)


def test_missing_required_and_unreadable(clients):
    problems = check(make(patient=None, unreadable=["shade"]), clients)
    assert any("patient" in p for p in problems)
    assert any("не уверена" in p for p in problems)


def test_unknown_clinic_is_flagged(clients):
    assert any("справочнике" in p for p in check(make(clinic="Helios +"), clients))


def test_doctor_from_other_clinic_is_flagged(clients):
    assert any("не работает" in p for p in check(make(doctor="Иванов С.С."), clients))  # Иванов — Дента-Люкс


def test_doctor_match_ignores_spaces_and_dots(clients):
    assert check(make(doctor="петрова а. в"), clients) == []


@pytest.mark.parametrize("path", TRUTH_FILES, ids=lambda p: p.name)
def test_review_only_for_sum_errors(path, clients):
    """Если модель прочитает всё идеально, на проверку уходят только наряды с ошибкой в сумме
    (06 — нарочно, 08 — на листе Ед. = 1)."""
    problems = check(Naryad.model_validate_json(path.read_text(encoding="utf-8")), clients)
    assert bool(problems) == (path.stem in ("naryad_06", "naryad_08"))
