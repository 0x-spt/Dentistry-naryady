"""Одно фото → таблица: подготовка, распознавание, проверки, запись.

Общий шаг для `naryad process` и Telegram-бота, чтобы оба входа вели себя одинаково.
"""

import threading
from dataclasses import dataclass
from pathlib import Path

from naryad.checks import check
from naryad.clients import Clients
from naryad.extractors import Extractor
from naryad.image import prepare
from naryad.schema import Naryad
from naryad.sheets import Sheet, write


@dataclass(frozen=True)
class Processed:
    naryad: Naryad
    problems: list[str]  # итоговые: проверки + дубль номера из таблицы
    action: str  # «добавлен» | «обновлён» | «пропущен»
    cropped: bool

    @property
    def needs_review(self) -> bool:
        return bool(self.problems)


class Pipeline:
    def __init__(self, extractor: Extractor, clients: Clients, naryady: Sheet, raboty: Sheet):
        self.extractor, self.clients = extractor, clients
        self.naryady, self.raboty = naryady, raboty
        # Распознавать можно параллельно, а писать — по одному: write читает таблицу, ищет строку
        # и дописывает. Два потока одновременно заняли бы одну и ту же «свободную» строку.
        self._write_lock = threading.Lock()

    def process(self, photo: Path) -> Processed:
        prepared = prepare(photo)
        n = self.extractor.extract(prepared.jpeg).naryad
        with self._write_lock:
            action, problems = write(self.naryady, self.raboty, n, check(n, self.clients), photo.name,
                                     self.extractor.model)
        return Processed(n, problems, action, prepared.cropped)
