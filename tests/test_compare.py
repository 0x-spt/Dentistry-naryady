from conftest import make

from naryad.compare import compare
from naryad.text import norm_shade, norm_text


def test_norm_text_ignores_spaces_dots_case():
    assert norm_text("Петрова А. В.") == norm_text("петрова а.в.")


def test_norm_shade_cyrillic_and_comma():
    assert norm_shade("А3,5") == "A3.5"  # первая «А» — кириллица


def test_compare_teeth_order_and_wrong_shade():
    result = compare(make(teeth=[21, 11], shade="B2"), make(teeth=[11, 21]))
    assert result["teeth"] is True
    assert result["shade"] is False
    assert all(ok for f, ok in result.items() if f != "shade")
