import json
from pathlib import Path

import pytest

from tfdo._internal.schema import inspect as schema_inspect
from tfdo._internal.schema.inspect_logic import SchemaShowInput, schema_show
from tfdo._internal.settings import TfDoSettings

_FIXTURE = Path(__file__).parent / "inspect_logic_test" / "minimal_schema.json"


def _fixture_dict() -> dict:
    return json.loads(_FIXTURE.read_text())


def test_schema_show_lists_resource_types(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(*_a: object, **_k: object) -> dict:
        return _fixture_dict()

    monkeypatch.setattr(schema_inspect, "fetch_providers_schema_json", fake_fetch)
    out = schema_show(SchemaShowInput(settings=TfDoSettings(), provider="mongodbatlas"))
    assert out.resource_names == ["mongodbatlas_cluster", "mongodbatlas_project"]
    assert out.resource is None


def test_schema_show_one_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(*_a: object, **_k: object) -> dict:
        return _fixture_dict()

    monkeypatch.setattr(schema_inspect, "fetch_providers_schema_json", fake_fetch)
    out = schema_show(
        SchemaShowInput(
            settings=TfDoSettings(),
            provider="mongodbatlas",
            source="mongodb/mongodbatlas",
            resource="mongodbatlas_cluster",
        )
    )
    assert out.resource
    assert out.resource.block.attributes
    assert out.resource.block.attributes["name"].required


def test_schema_show_unknown_resource_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(*_a: object, **_k: object) -> dict:
        return _fixture_dict()

    monkeypatch.setattr(schema_inspect, "fetch_providers_schema_json", fake_fetch)
    with pytest.raises(ValueError, match="not found"):
        schema_show(
            SchemaShowInput(
                settings=TfDoSettings(),
                provider="mongodbatlas",
                source="mongodb/mongodbatlas",
                resource="mongodbatlas_nope",
            )
        )
