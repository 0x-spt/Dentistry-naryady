from conftest import make

from naryad.bot import format_reply, parse_allowed
from naryad.pipeline import Processed


def test_parse_allowed():
    assert parse_allowed("123, 456,") == {123, 456}
    assert parse_allowed(None) == set() and parse_allowed("") == set()


def test_reply_ok():
    text = format_reply(Processed(make(number="101", patient="Сидорова И.П."), [], "добавлен", True))
    assert text.startswith("✅ Наряд №101 — записан")
    assert "пациент Сидорова И.П." in text and "18 000 ₽" in text and "сдача 28.10" in text


def test_reply_review_lists_reasons_and_crop_hint():
    text = format_reply(Processed(make(number=None), ["нет обязательного поля number"], "добавлен", False))
    assert text.startswith("⚠️ Наряд без номера — на проверку")
    assert "• нет обязательного поля number" in text
    assert "Лист на фото не нашёлся" in text


def test_reply_skipped():
    assert "уже проверен" in format_reply(Processed(make(), [], "пропущен", True))
