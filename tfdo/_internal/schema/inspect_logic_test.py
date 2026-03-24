import json
from pathlib import Path

import pytest

from tfdo._internal.schema import inspect as schema_inspect
from tfdo._internal.schema.inspect_logic import (
    SchemaShowInput,
    pick_provider_key,
    resolve_registry_source,
    schema_show,
)
from tfdo._internal.settings import TfDoSettings

_fetch_providers_schema_json = schema_inspect.fetch_providers_schema_json

_FIXTURE = Path(__file__).parent / "inspect_logic_test" / "minimal_schema.json"


def _fixture_dict() -> dict:
    return json.loads(_FIXTURE.read_text())


def _as_fetch(d: dict) -> schema_inspect.FetchProvidersSchemaResult:
    return schema_inspect.FetchProvidersSchemaResult(d, "1.0.0")


def test_schema_show_lists_resource_types(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(*_a: object, **_k: object) -> schema_inspect.FetchProvidersSchemaResult:
        return _as_fetch(_fixture_dict())

    monkeypatch.setattr(schema_inspect, _fetch_providers_schema_json.__name__, fake_fetch)
    out = schema_show(SchemaShowInput(settings=TfDoSettings(), provider="mongodbatlas"))
    assert out.resource_names == ["mongodbatlas_cluster", "mongodbatlas_project"]
    assert out.resource is None


def test_schema_show_one_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(*_a: object, **_k: object) -> schema_inspect.FetchProvidersSchemaResult:
        return _as_fetch(_fixture_dict())

    monkeypatch.setattr(schema_inspect, _fetch_providers_schema_json.__name__, fake_fetch)
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


def test_schema_show_passes_no_cache_to_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, bool] = {}

    def fake_fetch(
        _settings: object,
        *,
        local_name: str,
        source: str,
        version: str,
        no_cache: bool = False,
        schema_cache_root: object = None,
        use_dev_overrides: bool = True,
    ) -> schema_inspect.FetchProvidersSchemaResult:
        seen["no_cache"] = no_cache
        return _as_fetch(_fixture_dict())

    monkeypatch.setattr(schema_inspect, _fetch_providers_schema_json.__name__, fake_fetch)
    schema_show(
        SchemaShowInput(settings=TfDoSettings(), provider="mongodbatlas", no_cache=True),
    )
    assert seen["no_cache"]


def test_resolve_registry_source_unknown_provider_requires_explicit_source() -> None:
    with pytest.raises(ValueError, match="No default registry source"):
        resolve_registry_source(provider="custom", source=None)


def test_pick_provider_key_single_match_by_source_suffix() -> None:
    key = pick_provider_key(
        {"registry.terraform.io/hashicorp/aws": {"resource_schemas": {}}},
        local_name="aws",
        source="hashicorp/aws",
    )
    assert key == "registry.terraform.io/hashicorp/aws"


def test_pick_provider_key_unique_by_local_when_source_suffix_not_in_keys() -> None:
    key = pick_provider_key(
        {"registry.terraform.io/acme/aws": {}},
        local_name="aws",
        source="hashicorp/aws",
    )
    assert key == "registry.terraform.io/acme/aws"


def test_pick_provider_key_ambiguous_source_raises() -> None:
    schemas = {"a/hashicorp/aws": {}, "b/hashicorp/aws": {}}
    with pytest.raises(ValueError, match="Ambiguous provider keys for source"):
        pick_provider_key(schemas, local_name="aws", source="hashicorp/aws")


def test_pick_provider_key_ambiguous_local_raises() -> None:
    schemas = {"registry.terraform.io/acme/aws": {}, "registry.terraform.io/other/aws": {}}
    with pytest.raises(ValueError, match="Ambiguous provider keys for local name"):
        pick_provider_key(schemas, local_name="aws", source="hashicorp/aws")


def test_pick_provider_key_not_found_lists_sample_keys() -> None:
    with pytest.raises(ValueError, match="Provider not found"):
        pick_provider_key({"registry.terraform.io/hashicorp/google": {}}, local_name="aws", source="hashicorp/aws")


def test_schema_show_invalid_provider_schemas_type(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(*_a: object, **_k: object) -> schema_inspect.FetchProvidersSchemaResult:
        return _as_fetch({"provider_schemas": "nope"})

    monkeypatch.setattr(schema_inspect, _fetch_providers_schema_json.__name__, fake_fetch)
    with pytest.raises(ValueError, match="provider_schemas"):
        schema_show(SchemaShowInput(settings=TfDoSettings(), provider="mongodbatlas", source="mongodb/mongodbatlas"))


def test_schema_show_invalid_provider_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(*_a: object, **_k: object) -> schema_inspect.FetchProvidersSchemaResult:
        return _as_fetch({"provider_schemas": {"registry.terraform.io/mongodb/mongodbatlas": []}})

    monkeypatch.setattr(schema_inspect, _fetch_providers_schema_json.__name__, fake_fetch)
    with pytest.raises(ValueError, match="Invalid provider entry"):
        schema_show(SchemaShowInput(settings=TfDoSettings(), provider="mongodbatlas", source="mongodb/mongodbatlas"))


def test_schema_show_resource_schemas_not_dict_becomes_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(*_a: object, **_k: object) -> schema_inspect.FetchProvidersSchemaResult:
        return _as_fetch(
            {
                "provider_schemas": {
                    "registry.terraform.io/mongodb/mongodbatlas": {"resource_schemas": []},
                },
            }
        )

    monkeypatch.setattr(schema_inspect, _fetch_providers_schema_json.__name__, fake_fetch)
    out = schema_show(SchemaShowInput(settings=TfDoSettings(), provider="mongodbatlas", source="mongodb/mongodbatlas"))
    assert out.resource_names == []


def test_schema_show_result_to_canonical_json_includes_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(*_a: object, **_k: object) -> schema_inspect.FetchProvidersSchemaResult:
        return _as_fetch(_fixture_dict())

    monkeypatch.setattr(schema_inspect, _fetch_providers_schema_json.__name__, fake_fetch)
    out = schema_show(
        SchemaShowInput(
            settings=TfDoSettings(),
            provider="mongodbatlas",
            source="mongodb/mongodbatlas",
            resource="mongodbatlas_cluster",
        )
    )
    text = out.to_canonical_json()
    assert '"resource"' in text


def test_schema_show_unknown_resource_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(*_a: object, **_k: object) -> schema_inspect.FetchProvidersSchemaResult:
        return _as_fetch(_fixture_dict())

    monkeypatch.setattr(schema_inspect, _fetch_providers_schema_json.__name__, fake_fetch)
    with pytest.raises(ValueError, match="not found"):
        schema_show(
            SchemaShowInput(
                settings=TfDoSettings(),
                provider="mongodbatlas",
                source="mongodb/mongodbatlas",
                resource="mongodbatlas_nope",
            )
        )
