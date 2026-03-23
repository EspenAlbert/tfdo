import json
import logging
from pathlib import Path

import pytest

from tfdo._internal.inspect.resource_usage_logic import ResourceUsageInput, inspect_resource_usage
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
    monkeypatch.setattr(schema_inspect, _fetch.__name__, lambda *_a, **_k: _fixture())
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
    assert len(result.rows) == 1
    assert result.rows[0].included == ["name"]
    assert result.errors
    skipping = [r for r in caplog.records if "Skipping" in r.message]
    assert len(skipping) == 1
    assert "mongodbatlas_not_in_fixture" in skipping[0].message


def test_inspect_resource_usage_include_patterns(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(schema_inspect, _fetch.__name__, lambda *_a, **_k: _fixture())
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
    assert len(result.rows) == 1
    assert result.rows[0].address == "mongodbatlas_cluster.c"


def test_inspect_resource_usage_rejects_no_input_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(schema_inspect, _fetch.__name__, lambda *_a, **_k: _fixture())
    with pytest.raises(ValueError, match="Omit --no-input-only"):
        inspect_resource_usage(
            ResourceUsageInput(
                settings=TfDoSettings(),
                root=tmp_path,
                provider="mongodbatlas",
                input_only=False,
            )
        )
