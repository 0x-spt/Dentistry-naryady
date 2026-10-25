"""Прогон целиком без сети: вместо модели — заглушка, которая отвечает эталоном."""

import shutil

from conftest import DATA
from PIL import Image

from naryad.evaluation import evaluate
from naryad.extractors import Extraction, fingerprint
from naryad.schema import Naryad


class StubExtractor:
    model, system = "stub-model", "stub prompt"

    def __init__(self, answers: dict[str, Naryad]):
        self.answers, self.calls = answers, 0
        self.queue = list(answers.values())

    def extract(self, jpeg: bytes) -> Extraction:
        self.calls += 1
        return Extraction(self.queue.pop(0), 100, 10)


def dataset(tmp_path, names):
    photos, truth = tmp_path / "photos", tmp_path / "truth"
    photos.mkdir()
    truth.mkdir()
    answers = {}
    for name in names:
        Image.new("RGB", (300, 400), "white").save(photos / f"{name}.jpg")
        shutil.copy(DATA / "truth" / f"{name}.json", truth)
        answers[name] = Naryad.model_validate_json((truth / f"{name}.json").read_text(encoding="utf-8"))
    return photos, truth, answers


def test_perfect_answers(tmp_path, clients):
    photos, truth, answers = dataset(tmp_path, ["naryad_01", "naryad_06"])
    report = evaluate(StubExtractor(answers), clients, photos, truth, tmp_path / "results")
    assert report.accuracy == 1.0
    assert report.silent_errors == 0
    assert [i.needs_review for i in report.items] == [False, True]  # 06 — ошибка в сумме
    assert report.cost is None  # цены stub-model нет в PRICES


def test_silent_error_is_counted(tmp_path, clients):
    photos, truth, answers = dataset(tmp_path, ["naryad_01"])
    # Врач из справочника, но не тот — проверки молчат, а это ошибка
    answers["naryad_01"] = answers["naryad_01"].model_copy(update={"doctor": "Смирнова О.Л."})
    report = evaluate(StubExtractor(answers), clients, photos, truth, tmp_path / "results")
    assert report.silent_errors == 1
    assert report.items[0].fields["doctor"] is False


def test_second_run_uses_cache(tmp_path, clients):
    photos, truth, answers = dataset(tmp_path, ["naryad_01"])
    evaluate(StubExtractor(answers), clients, photos, truth, tmp_path / "results")
    again = StubExtractor(answers)
    evaluate(again, clients, photos, truth, tmp_path / "results")
    assert again.calls == 0


def test_fingerprint_changes_with_prompt():
    a, b = StubExtractor({}), StubExtractor({})
    b.system = "другой промпт"
    assert fingerprint(a, crop=True) != fingerprint(b, crop=True)
    assert fingerprint(a, crop=True) != fingerprint(a, crop=False)
