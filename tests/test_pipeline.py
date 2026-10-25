"""Фото → таблица целиком: настоящая подготовка фото, заглушка модели, лист в памяти."""

import threading
import time

from conftest import FakeSheet, make
from PIL import Image

from naryad.extractors import Extraction
from naryad.pipeline import Pipeline


class SlowStub:
    """Отвечает заданным нарядом с задержкой — чтобы потоки реально пересекались."""

    model, system = "stub-model", ""

    def __init__(self, naryad, delay=0.0):
        self.naryad, self.delay = naryad, delay

    def extract(self, jpeg):
        time.sleep(self.delay)
        return Extraction(self.naryad, 0, 0)


def photo(tmp_path, name):
    path = tmp_path / name
    Image.new("RGB", (300, 400), "white").save(path)
    return path


def test_process_writes_and_reports(tmp_path, clients):
    naryady, raboty = FakeSheet(), FakeSheet()
    r = Pipeline(SlowStub(make(number="101", total=1)), clients, naryady, raboty).process(photo(tmp_path, "a.jpg"))
    assert r.action == "добавлен" and r.needs_review  # итог 1 ≠ 18000
    assert naryady.rows[1][0] == "№101"


def test_parallel_photos_get_separate_rows(tmp_path, clients):
    naryady, raboty = FakeSheet(), FakeSheet()
    pipelines = [Pipeline(SlowStub(make(number=str(100 + i)), delay=0.05), clients, naryady, raboty)
                 for i in range(5)]
    # один общий замок на запись, как в боте: все потоки пишут через один Pipeline
    shared = pipelines[0]
    threads = []
    for i, p in enumerate(pipelines):
        p._write_lock = shared._write_lock
        threads.append(threading.Thread(target=p.process, args=(photo(tmp_path, f"{i}.jpg"),)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(r[0] for r in naryady.rows[1:]) == [f"№{100 + i}" for i in range(5)]
    assert naryady.rows[0][0] == "Ключ" and sum(r[0] == "Ключ" for r in naryady.rows) == 1
