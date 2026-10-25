"""Нормализация строк: одно и то же значение, записанное по-разному, должно совпадать."""

CYR_TO_LAT = str.maketrans("АВСЕ", "ABCE")  # кириллическая «А2» выглядит как латинская A2


def norm_text(s: str | None) -> str | None:
    """«Петрова А. В.» и «петрова а.в.» — одно и то же."""
    if s is None:
        return None
    return s.lower().replace("ё", "е").replace(" ", "").replace(".", "")


def norm_shade(s: str | None) -> str | None:
    """«А3,5» (кириллица, запятая) → «A3.5»."""
    if s is None:
        return None
    return s.upper().translate(CYR_TO_LAT).replace(",", ".").replace(" ", "")
