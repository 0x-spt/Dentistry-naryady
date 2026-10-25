"""Распознавание: картинка → Naryad.

Остальной код зависит от протокола Extractor, а не от конкретного клиента:
в тестах вместо модели подставляется заглушка, и прогон проверяется без сети и денег.
"""

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

import anthropic

from naryad.image import PREPROCESS_VERSION
from naryad.schema import Naryad

DEFAULT_MODEL = "claude-opus-5-5"
# $ за миллион токенов (вход, выход)
PRICES = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50)}


@dataclass(frozen=True)
class Extraction:
    naryad: Naryad
    input_tokens: int
    output_tokens: int


class Extractor(Protocol):
    model: str
    system: str

    def extract(self, jpeg: bytes) -> Extraction: ...


def fingerprint(ex: Extractor, crop: bool) -> str:
    """Отпечаток всего, что влияет на ответ модели. Поменялся промпт, схема или обработка
    фото — меняется отпечаток, и старый кэш больше не подхватывается молча."""
    parts = [ex.model, ex.system, json.dumps(Naryad.model_json_schema()), PREPROCESS_VERSION, str(crop)]
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()[:10]


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    if model not in PRICES:
        return None
    price_in, price_out = PRICES[model]
    return (input_tokens * price_in + output_tokens * price_out) / 1e6


class ApiExtractor:
    """Messages API + structured outputs. Ключ — из ANTHROPIC_API_KEY."""

    def __init__(self, system: str, model: str = DEFAULT_MODEL, client: anthropic.Anthropic | None = None):
        self.system, self.model = system, model
        self.client = client or anthropic.Anthropic()

    def extract(self, jpeg: bytes) -> Extraction:
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=16000,
            system=self.system,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/jpeg",
                        "data": base64.standard_b64encode(jpeg).decode(),
                    }},
                    {"type": "text", "text": "Распознай этот наряд."},
                ],
            }],
            output_format=Naryad,
        )
        return Extraction(response.parsed_output, response.usage.input_tokens, response.usage.output_tokens)
