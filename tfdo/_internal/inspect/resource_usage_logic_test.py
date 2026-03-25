import json
import logging
from pathlib import Path

import pytest

from tfdo._internal.inspect.resource_usage_logic import (
    ResourceUsageInput,
    SchemaSearch,
    inspect_resource_usage,
    schema_search_from_cli_and_optional_file,
)
from tfdo._internal.inspect.schema_input_classify_logic import SchemaInputClassifyMode
from tfdo._internal.schema import inspect as schema_inspect
from tfdo._internal.settings import TfDoSettings

_fetch = schema_inspect.fetch_providers_schema_json
_FIXTURE = Path(__file__).resolve().parent.parent / "schema" / "inspect_logic_test" / "minimal_schema.json"


def _fixture() -> dict:
    return json.loads(_FIXTURE.read_text())


def test_inspect_resource_usage_included_and_skips_unknown_type(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        schema_inspect,
        _fetch.__name__,
        lambda *_a, **_k: schema_inspect.FetchProvidersSchemaResult(_fixture(), "1.0.0"),
    )
    (tmp_path / "main.tf").write_text(
        'resource "mongodbatlas_cluster" "c" {\n  name = "n"\n}\n'
        'resource "aws_instance" "x" {}\n'
        'resource "mongodbatlas_not_in_fixture" "u" {}\n',
        encoding="utf-8",
    )
    (tmp_path / "bad.tf").write_text("not hcl {{\n", encoding="utf-8")
    caplog.set_level(logging.WARNING)
    result = inspect_resource_usage(
        ResourceUsageInput(
            settings=TfDoSettings(),
            root=tmp_path,
            provider="mongodbatlas",
            mode=SchemaInputClassifyMode.INCLUDED,
        )
    )
    assert len(result.classify.rows) == 1
    assert result.classify.rows[0].included == ["name"]
    assert result.classify.errors
    meta = result.providers["mongodbatlas"]
    assert meta.source == "mongodb/mongodbatlas"
    assert meta.version == "1.0.0"
    payload = json.loads(result.to_canonical_json())
    assert payload["providers"]["mongodbatlas"] == {"source": "mongodb/mongodbatlas", "version": "1.0.0"}
    skipping = [r for r in caplog.records if "Skipping" in r.message]
    assert len(skipping) == 1
    assert "mongodbatlas_not_in_fixture" in skipping[0].message


def test_inspect_resource_usage_include_patterns(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        schema_inspect,
        _fetch.__name__,
        lambda *_a, **_k: schema_inspect.FetchProvidersSchemaResult(_fixture(), "1.0.0"),
    )
    keep = tmp_path / "keep" / "a.tf"
    keep.parent.mkdir(parents=True)
    keep.write_text('resource "mongodbatlas_cluster" "c" { name = "n" }\n', encoding="utf-8")
    other = tmp_path / "other" / "b.tf"
    other.parent.mkdir(parents=True)
    other.write_text('resource "mongodbatlas_cluster" "d" { name = "x" }\n', encoding="utf-8")
    result = inspect_resource_usage(
        ResourceUsageInput(
            settings=TfDoSettings(),
            root=tmp_path,
            provider="mongodbatlas",
            include_patterns=["keep"],
            mode=SchemaInputClassifyMode.INCLUDED,
        )
    )
    assert len(result.classify.rows) == 1
    assert result.classify.rows[0].address == "mongodbatlas_cluster.c"
    assert result.providers["mongodbatlas"].version == "1.0.0"


def test_inspect_resource_usage_with_description_keywords(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        schema_inspect,
        _fetch.__name__,
        lambda *_a, **_k: schema_inspect.FetchProvidersSchemaResult(_fixture(), "1.0.0"),
    )
    (tmp_path / "main.tf").write_text(
        'resource "mongodbatlas_cluster" "c" { name = "n" }\n',
        encoding="utf-8",
    )
    result = inspect_resource_usage(
        ResourceUsageInput(
            settings=TfDoSettings(),
            root=tmp_path,
            provider="mongodbatlas",
            schema_search=SchemaSearch(description_keywords=["name"]),
        )
    )
    assert result.matching_schema_resources is not None
    assert len(result.matching_schema_resources) == 1
    match = result.matching_schema_resources[0]
    assert match.name == "mongodbatlas_cluster"
    assert match.found_in_rows
    assert match.matching_attribute_descriptions[0].keywords == ["name"]
    payload = json.loads(result.to_canonical_json())
    assert "matching_schema_resources" in payload
    assert payload["matching_schema_resources"][0]["name"] == "mongodbatlas_cluster"


def test_inspect_resource_usage_description_search_respects_resource_ignore(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        schema_inspect,
        _fetch.__name__,
        lambda *_a, **_k: schema_inspect.FetchProvidersSchemaResult(_fixture(), "1.0.0"),
    )
    (tmp_path / "main.tf").write_text(
        'resource "mongodbatlas_cluster" "c" { name = "n" }\n',
        encoding="utf-8",
    )
    result = inspect_resource_usage(
        ResourceUsageInput(
            settings=TfDoSettings(),
            root=tmp_path,
            provider="mongodbatlas",
            schema_search=SchemaSearch(
                description_keywords=["name"],
                resource_ignore=["mongodbatlas_cluster"],
            ),
        )
    )
    assert result.matching_schema_resources is not None
    assert result.matching_schema_resources == []


def test_inspect_resource_usage_no_schema_search_omits_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        schema_inspect,
        _fetch.__name__,
        lambda *_a, **_k: schema_inspect.FetchProvidersSchemaResult(_fixture(), "1.0.0"),
    )
    (tmp_path / "main.tf").write_text(
        'resource "mongodbatlas_cluster" "c" { name = "n" }\n',
        encoding="utf-8",
    )
    result = inspect_resource_usage(
        ResourceUsageInput(
            settings=TfDoSettings(),
            root=tmp_path,
            provider="mongodbatlas",
        )
    )
    assert result.matching_schema_resources is None
    payload = json.loads(result.to_canonical_json())
    assert "matching_schema_resources" not in payload


def test_schema_search_from_file_only(tmp_path: Path) -> None:
    cfg = tmp_path / "search.json"
    cfg.write_text(
        '{"description_keywords": ["name"], "resource_ignore": ["mongodbatlas_cluster"]}\n',
        encoding="utf-8",
    )
    got = schema_search_from_cli_and_optional_file(
        schema_search_path=cfg,
        cli_keywords=[],
        cli_resource_ignore=[],
    )
    assert got is not None
    assert got.description_keywords == ["name"]
    assert got.resource_ignore == ["mongodbatlas_cluster"]


def test_schema_search_cli_keywords_override_file(tmp_path: Path) -> None:
    cfg = tmp_path / "search.json"
    cfg.write_text('{"description_keywords": ["from_file"]}\n', encoding="utf-8")
    got = schema_search_from_cli_and_optional_file(
        schema_search_path=cfg,
        cli_keywords=["from_cli"],
        cli_resource_ignore=[],
    )
    assert got is not None
    assert got.description_keywords == ["from_cli"]


def test_schema_search_cli_ignores_override_file(tmp_path: Path) -> None:
    cfg = tmp_path / "search.json"
    cfg.write_text(
        '{"description_keywords": ["k"], "resource_ignore": ["a", "b"]}\n',
        encoding="utf-8",
    )
    got = schema_search_from_cli_and_optional_file(
        schema_search_path=cfg,
        cli_keywords=[],
        cli_resource_ignore=["c"],
    )
    assert got is not None
    assert got.description_keywords == ["k"]
    assert got.resource_ignore == ["c"]


def test_schema_search_cli_keywords_merge_keeps_file_ignores(tmp_path: Path) -> None:
    cfg = tmp_path / "search.json"
    cfg.write_text(
        '{"description_keywords": ["old"], "resource_ignore": ["mongodbatlas_cluster"]}\n',
        encoding="utf-8",
    )
    got = schema_search_from_cli_and_optional_file(
        schema_search_path=cfg,
        cli_keywords=["new_kw"],
        cli_resource_ignore=[],
    )
    assert got is not None
    assert got.description_keywords == ["new_kw"]
    assert got.resource_ignore == ["mongodbatlas_cluster"]


def test_schema_search_preserves_include_data_sources_from_file(tmp_path: Path) -> None:
    cfg = tmp_path / "search.json"
    cfg.write_text(
        '{"description_keywords": ["x"], "include_data_sources": true}\n',
        encoding="utf-8",
    )
    got = schema_search_from_cli_and_optional_file(
        schema_search_path=cfg,
        cli_keywords=["y"],
        cli_resource_ignore=[],
    )
    assert got is not None
    assert got.include_data_sources


def test_schema_search_no_file_no_keywords() -> None:
    assert (
        schema_search_from_cli_and_optional_file(
            schema_search_path=None,
            cli_keywords=[],
            cli_resource_ignore=[],
        )
        is None
    )


def test_schema_search_file_without_keywords_returns_none(tmp_path: Path) -> None:
    cfg = tmp_path / "search.json"
    cfg.write_text('{"resource_ignore": ["mongodbatlas_cluster"]}\n', encoding="utf-8")
    assert (
        schema_search_from_cli_and_optional_file(
            schema_search_path=cfg,
            cli_keywords=[],
            cli_resource_ignore=[],
        )
        is None
    )


def test_inspect_resource_usage_rejects_no_input_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        schema_inspect,
        _fetch.__name__,
        lambda *_a, **_k: schema_inspect.FetchProvidersSchemaResult(_fixture(), "1.0.0"),
    )
    with pytest.raises(ValueError, match="Omit --no-input-only"):
        inspect_resource_usage(
            ResourceUsageInput(
                settings=TfDoSettings(),
                root=tmp_path,
                provider="mongodbatlas",
                input_only=False,
            )
        )
