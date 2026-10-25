"""Схема наряда: что модель обязана вернуть с фото.

Схема описывает то, что НАПИСАНО на бланке, а не то, что правильно.
Правильность (сумма, номера зубов, даты) проверяет checks.py — иначе
один неверный итог уничтожил бы все остальные распознанные поля.

Все поля обязательные, но могут быть null: модель должна явно сказать
«поля нет», а не молча его пропустить.
"""
from datetime import date

from pydantic import BaseModel, Field


class WorkItem(BaseModel):
    """Одна строка таблицы работ."""

    name: str = Field(description="Вид работы, как написано: «коронка», «мост», «винир» и т.п.")
    material: str | None = Field(
        description="Материал (цирконий, E.max, металлокерамика/МК, КХС…); null если не указан"
    )
    qty: int | None = Field(description="Количество единиц; null если не указано")
    unit_price: int | None = Field(
        description="Цена ЗА ЕДИНИЦУ в целых рублях. «1,5 т.р.» = 1500, «9 000» = 9000. "
        "Если указана только общая цена строки — раздели на количество. null если цены нет"
    )


class Naryad(BaseModel):
    """Заказ-наряд зуботехнической лаборатории."""

    number: str | None = Field(description="Номер наряда как написан, строкой (может быть «0102», «102/А»)")
    issued: date | None = Field(description="Дата наряда (поле «от»)")
    clinic: str | None = Field(description="Название клиники")
    doctor: str | None = Field(description="Врач: фамилия и инициалы как написаны")
    patient: str | None = Field(description="Пациент: фамилия и инициалы как написаны")
    technician: str | None = Field(description="Техник; null если поле пустое")
    teeth: list[int] = Field(
        description="Номера зубов по FDI (11–18, 21–28, 31–38, 41–48). Диапазон «14-16» раскрыть в [14, 15, 16]. "
        "Пустой список, если зубы не указаны"
    )
    works: list[WorkItem] = Field(description="Все строки работ по порядку")
    shade: str | None = Field(description="Цвет по шкале VITA латиницей: A1, A3.5, B2…")
    total: int | None = Field(description="Итог в целых рублях ТАК, КАК НАПИСАН на бланке. Не пересчитывай сам")
    fitting_date: date | None = Field(description="Дата примерки; null если пусто или прочерк")
    due_date: date | None = Field(description="Дата сдачи")
    note: str | None = Field(description="Примечание; null если пусто")
    unreadable: list[str] = Field(
        description="Имена полей этой схемы, которые на фото есть, но прочитать уверенно нельзя. "
        "Пустой список, если всё прочитано"
    )
