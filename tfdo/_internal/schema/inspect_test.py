from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tfdo._internal.schema import inspect as schema_inspect
from tfdo._internal.settings import TfDoSettings


def test_schema_cache_dir_uses_schemas_leaf() -> None:
    assert TfDoSettings().schema_cache_dir.name == "schemas"


def test_fetch_providers_schema_json_cache_hit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = {"format_version": "1.0", "provider_schemas": {}}
    monkeypatch.setattr(schema_inspect.executor, "init", MagicMock(return_value=MagicMock(exit_code=0)))
    monkeypatch.setattr(
        schema_inspect.schema_cache,
        "read_resolved_version_from_lock",
        lambda **_: "1.0.0",
    )
    monkeypatch.setattr(schema_inspect.schema_cache, "try_read_cached_schema", lambda _p: payload)
    run_mock = MagicMock()
    monkeypatch.setattr(schema_inspect, "run_and_wait", run_mock)
    out = schema_inspect.fetch_providers_schema_json(
        TfDoSettings(),
        local_name="aws",
        source="hashicorp/aws",
        version=">= 1.0",
        schema_cache_root=tmp_path,
    )
    assert out is payload
    run_mock.assert_not_called()


def test_fetch_providers_schema_json_miss_writes_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = {"format_version": "1.0", "provider_schemas": {}}
    monkeypatch.setattr(schema_inspect.executor, "init", MagicMock(return_value=MagicMock(exit_code=0)))
    monkeypatch.setattr(
        schema_inspect.schema_cache,
        "read_resolved_version_from_lock",
        lambda **_: "1.0.0",
    )
    monkeypatch.setattr(schema_inspect.schema_cache, "try_read_cached_schema", lambda _p: None)
    write_mock = MagicMock()
    monkeypatch.setattr(schema_inspect.schema_cache, "write_cached_schema", write_mock)
    run = MagicMock(exit_code=0)
    run.parse_output = MagicMock(return_value=payload)
    monkeypatch.setattr(schema_inspect, "run_and_wait", MagicMock(return_value=run))
    out = schema_inspect.fetch_providers_schema_json(
        TfDoSettings(),
        local_name="aws",
        source="hashicorp/aws",
        version=">= 1.0",
        schema_cache_root=tmp_path,
    )
    assert out == payload
    write_mock.assert_called_once()
    run.parse_output.assert_called_once_with(dict, output_format="json")


def test_fetch_providers_schema_json_unresolved_version_skips_cache_io(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = {"provider_schemas": {}}
    monkeypatch.setattr(schema_inspect.executor, "init", MagicMock(return_value=MagicMock(exit_code=0)))
    monkeypatch.setattr(schema_inspect.schema_cache, "read_resolved_version_from_lock", lambda **_: None)
    try_read = MagicMock()
    monkeypatch.setattr(schema_inspect.schema_cache, "try_read_cached_schema", try_read)
    write_mock = MagicMock()
    monkeypatch.setattr(schema_inspect.schema_cache, "write_cached_schema", write_mock)
    run = MagicMock(exit_code=0)
    run.parse_output = MagicMock(return_value=payload)
    monkeypatch.setattr(schema_inspect, "run_and_wait", MagicMock(return_value=run))
    schema_inspect.fetch_providers_schema_json(
        TfDoSettings(),
        local_name="aws",
        source="hashicorp/aws",
        version=">= 1.0",
        schema_cache_root=tmp_path,
    )
    try_read.assert_not_called()
    write_mock.assert_not_called()


def test_fetch_providers_schema_json_no_cache_skips_cache_io(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = {"provider_schemas": {}}
    monkeypatch.setattr(schema_inspect.executor, "init", MagicMock(return_value=MagicMock(exit_code=0)))
    monkeypatch.setattr(
        schema_inspect.schema_cache,
        "read_resolved_version_from_lock",
        lambda **_: "1.0.0",
    )
    try_read = MagicMock()
    monkeypatch.setattr(schema_inspect.schema_cache, "try_read_cached_schema", try_read)
    write_mock = MagicMock()
    monkeypatch.setattr(schema_inspect.schema_cache, "write_cached_schema", write_mock)
    run = MagicMock(exit_code=0)
    run.parse_output = MagicMock(return_value=payload)
    monkeypatch.setattr(schema_inspect, "run_and_wait", MagicMock(return_value=run))
    schema_inspect.fetch_providers_schema_json(
        TfDoSettings(),
        local_name="aws",
        source="hashicorp/aws",
        version=">= 1.0",
        no_cache=True,
        schema_cache_root=tmp_path,
    )
    try_read.assert_not_called()
    write_mock.assert_not_called()


def test_fetch_providers_schema_json_init_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schema_inspect.executor, "init", MagicMock(return_value=MagicMock(exit_code=1)))
    with pytest.raises(RuntimeError, match="terraform init failed"):
        schema_inspect.fetch_providers_schema_json(
            TfDoSettings(),
            local_name="aws",
            source="hashicorp/aws",
            version=">= 1.0",
        )
