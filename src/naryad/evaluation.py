"""Прогон набора фото: распознать → проверить → сравнить с эталоном → метрики.

Ключевые метрики:
- accuracy — доля верно распознанных полей;
- review_rate — доля нарядов, ушедших человеку. Высокая = автоматизация ничего не экономит;
- silent_errors — наряды со статусом «ОК», но с ошибкой. Самое опасное: попадают в таблицу незамеченными.
"""

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from naryad.checks import check
from naryad.clients import Clients
from naryad.compare import GRADED, compare
from naryad.extractors import Extraction, Extractor, cost_usd, fingerprint
from naryad.image import prepare
from naryad.schema import Naryad

log = logging.getLogger(__name__)
PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png"}


@dataclass
class ItemResult:
    name: str
    naryad: Naryad
    problems: list[str]
    truth: Naryad | None  # None — эталона нет
    fields: dict[str, bool] | None
    cropped: bool

    @property
    def needs_review(self) -> bool:
        return bool(self.problems)

    @property
    def silent_error(self) -> bool:
        return not self.needs_review and self.fields is not None and not all(self.fields.values())


@dataclass
class Report:
    items: list[ItemResult] = field(default_factory=list)
    cost: float | None = None  # $ за прогон по ценам API; None — цена модели неизвестна

    @property
    def graded(self) -> list[ItemResult]:
        return [i for i in self.items if i.fields is not None]

    @property
    def per_field(self) -> dict[str, int]:
        c = Counter()
        for item in self.graded:
            c.update(f for f, ok in item.fields.items() if ok)
        return {f: c[f] for f in GRADED}

    @property
    def accuracy(self) -> float:
        total = len(self.graded) * len(GRADED)
        return sum(self.per_field.values()) / total if total else 0.0

    @property
    def review_rate(self) -> float:
        return sum(i.needs_review for i in self.items) / len(self.items) if self.items else 0.0

    @property
    def silent_errors(self) -> int:
        return sum(i.silent_error for i in self.items)


def find_photos(photos_dir: Path) -> list[Path]:
    return sorted(p for p in photos_dir.iterdir() if p.suffix.lower() in PHOTO_SUFFIXES)


def extract_cached(
    extractor: Extractor, photo: Path, cache_dir: Path, crop: bool, fresh: bool
) -> tuple[Extraction, bool]:
    """Ответ модели из кэша или новый вызов. Кэш лежит в папке с отпечатком конфигурации,
    поэтому правка checks/compare не стоит денег, а правка промпта не подхватит старые ответы."""
    cached = cache_dir / f"{photo.stem}.json"
    prepared = prepare(photo, crop=crop)
    if cached.exists() and not fresh:
        data = json.loads(cached.read_text(encoding="utf-8"))
        return Extraction(Naryad.model_validate(data["naryad"]), **data["usage"]), prepared.cropped
    log.info("распознаю %s (%s)", photo.name, extractor.model)
    ex = extractor.extract(prepared.jpeg)
    cached.write_text(json.dumps({
        "naryad": ex.naryad.model_dump(mode="json"),
        "usage": {"input_tokens": ex.input_tokens, "output_tokens": ex.output_tokens},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return ex, prepared.cropped


def evaluate(extractor: Extractor, clients: Clients, photos_dir: Path, truth_dir: Path, results_dir: Path,
             crop: bool = True, fresh: bool = False) -> Report:
    photos = find_photos(photos_dir)
    if not photos:
        raise FileNotFoundError(f"в {photos_dir} нет фото ({', '.join(sorted(PHOTO_SUFFIXES))})")

    cache_dir = results_dir / extractor.model / fingerprint(extractor, crop)
    cache_dir.mkdir(parents=True, exist_ok=True)
    report, costs = Report(), []

    for photo in photos:
        ex, cropped = extract_cached(extractor, photo, cache_dir, crop, fresh)
        costs.append(cost_usd(extractor.model, ex.input_tokens, ex.output_tokens))
        truth_file = truth_dir / f"{photo.stem}.json"
        truth = (Naryad.model_validate_json(truth_file.read_text(encoding="utf-8"))
                 if truth_file.exists() else None)
        fields = compare(ex.naryad, truth) if truth else None
        report.items.append(ItemResult(photo.name, ex.naryad, check(ex.naryad, clients), truth, fields, cropped))

    # Неизвестная цена модели — None, а не враньё «$0»
    report.cost = None if None in costs else sum(costs)
    return report
