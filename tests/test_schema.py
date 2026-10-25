import pytest
from conftest import TRUTH_FILES

from naryad.schema import Naryad


@pytest.mark.parametrize("path", TRUTH_FILES, ids=lambda p: p.name)
def test_truth_files_match_schema(path):
    Naryad.model_validate_json(path.read_text(encoding="utf-8"))


def test_all_fields_required():
    """Модель обязана явно вернуть каждое поле, даже если там null."""
    schema = Naryad.model_json_schema()
    assert set(schema["required"]) == set(schema["properties"])
