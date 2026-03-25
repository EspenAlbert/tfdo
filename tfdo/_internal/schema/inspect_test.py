from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from ask_shell.shell import ShellError, ShellRun

from tfdo._internal.models import InitResult
from tfdo._internal.schema import inspect as schema_inspect
from tfdo._internal.schema import terraform_cli_config as tf_cli
from tfdo._internal.settings import TfDoSettings

_executor_init = schema_inspect.executor.init
_read_resolved_version_from_lock = schema_inspect.schema_cache.read_resolved_version_from_lock
_try_read_cached_schema = schema_inspect.schema_cache.try_read_cached_schema
_write_cached_schema = schema_inspect.schema_cache.write_cached_schema
_run_and_wait = schema_inspect.run_and_wait


@pytest.fixture(autouse=True)
def clear_tf_cli_config_file_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(tf_cli.TF_CLI_CONFIG_FILE_ENV, raising=False)


def test_schema_cache_dir_uses_schemas_leaf() -> None:
    assert TfDoSettings().schema_cache_dir.name == "schemas"


def test_fetch_tf_cli_config_file_skips_cache_and_sets_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = tmp_path / "user.tfrc"
    cfg.write_text(
        """provider_installation {
  dev_overrides = {
    "hashicorp/aws" = "/plugins"
  }
  direct {}
}
""",
        encoding="utf-8",
    )
    monkeypatch.setenv(tf_cli.TF_CLI_CONFIG_FILE_ENV, str(cfg))
    payload = {"provider_schemas": {}}
    init_mock = MagicMock(return_value=MagicMock(exit_code=0))
    monkeypatch.setattr(schema_inspect.executor, _executor_init.__name__, init_mock)
    monkeypatch.setattr(
        schema_inspect.schema_cache,
        _read_resolved_version_from_lock.__name__,
        lambda **_: "1.0.0",
    )
    try_read = MagicMock()
    monkeypatch.setattr(schema_inspect.schema_cache, _try_read_cached_schema.__name__, try_read)
    write_mock = MagicMock()
    monkeypatch.setattr(schema_inspect.schema_cache, _write_cached_schema.__name__, write_mock)
    run = MagicMock(exit_code=0)
    run.parse_output = MagicMock(return_value=payload)
    run_mock = MagicMock(return_value=run)
    monkeypatch.setattr(schema_inspect, _run_and_wait.__name__, run_mock)
    schema_inspect.fetch_providers_schema_json(
        TfDoSettings(),
        local_name="aws",
        source="hashicorp/aws",
        version=">= 1.0",
        schema_cache_root=tmp_path,
    )
    try_read.assert_not_called()
    write_mock.assert_not_called()
    init_mock.assert_not_called()
    run_env = run_mock.call_args.kwargs.get("env")
    assert run_env is not None
    assert tf_cli.TF_CLI_CONFIG_FILE_ENV in run_env
    assert run_env[tf_cli.TF_CLI_CONFIG_FILE_ENV].endswith("tfdo.dev.tfrc")


def test_fetch_providers_schema_json_cache_hit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = {"format_version": "1.0", "provider_schemas": {}}
    monkeypatch.setattr(
        schema_inspect.executor, _executor_init.__name__, MagicMock(return_value=MagicMock(exit_code=0))
    )
    monkeypatch.setattr(
        schema_inspect.schema_cache,
        _read_resolved_version_from_lock.__name__,
        lambda **_: "1.0.0",
    )
    monkeypatch.setattr(schema_inspect.schema_cache, _try_read_cached_schema.__name__, lambda _p: payload)
    run_mock = MagicMock()
    monkeypatch.setattr(schema_inspect, _run_and_wait.__name__, run_mock)
    out = schema_inspect.fetch_providers_schema_json(
        TfDoSettings(),
        local_name="aws",
        source="hashicorp/aws",
        version=">= 1.0",
        schema_cache_root=tmp_path,
    )
    assert out.payload is payload
    run_mock.assert_not_called()


def test_fetch_providers_schema_json_miss_writes_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = {"format_version": "1.0", "provider_schemas": {}}
    monkeypatch.setattr(
        schema_inspect.executor, _executor_init.__name__, MagicMock(return_value=MagicMock(exit_code=0))
    )
    monkeypatch.setattr(
        schema_inspect.schema_cache,
        _read_resolved_version_from_lock.__name__,
        lambda **_: "1.0.0",
    )
    monkeypatch.setattr(schema_inspect.schema_cache, _try_read_cached_schema.__name__, lambda _p: None)
    write_mock = MagicMock()
    monkeypatch.setattr(schema_inspect.schema_cache, _write_cached_schema.__name__, write_mock)
    run = MagicMock(exit_code=0)
    run.parse_output = MagicMock(return_value=payload)
    monkeypatch.setattr(schema_inspect, _run_and_wait.__name__, MagicMock(return_value=run))
    out = schema_inspect.fetch_providers_schema_json(
        TfDoSettings(),
        local_name="aws",
        source="hashicorp/aws",
        version=">= 1.0",
        schema_cache_root=tmp_path,
    )
    assert out.payload == payload
    write_mock.assert_called_once()
    run.parse_output.assert_called_once_with(dict, output_format="json")


def test_fetch_providers_schema_json_bad_lock_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        schema_inspect.executor, _executor_init.__name__, MagicMock(return_value=MagicMock(exit_code=0))
    )
    monkeypatch.setattr(
        schema_inspect.schema_cache,
        _read_resolved_version_from_lock.__name__,
        MagicMock(side_effect=ValueError("no provider in lock")),
    )
    try_read = MagicMock()
    monkeypatch.setattr(schema_inspect.schema_cache, _try_read_cached_schema.__name__, try_read)
    write_mock = MagicMock()
    monkeypatch.setattr(schema_inspect.schema_cache, _write_cached_schema.__name__, write_mock)
    run = MagicMock(exit_code=0)
    run.parse_output = MagicMock(return_value={"provider_schemas": {}})
    monkeypatch.setattr(schema_inspect, _run_and_wait.__name__, MagicMock(return_value=run))
    with pytest.raises(ValueError, match="no provider in lock"):
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
    monkeypatch.setattr(
        schema_inspect.executor, _executor_init.__name__, MagicMock(return_value=MagicMock(exit_code=0))
    )
    monkeypatch.setattr(
        schema_inspect.schema_cache,
        _read_resolved_version_from_lock.__name__,
        lambda **_: "1.0.0",
    )
    try_read = MagicMock()
    monkeypatch.setattr(schema_inspect.schema_cache, _try_read_cached_schema.__name__, try_read)
    write_mock = MagicMock()
    monkeypatch.setattr(schema_inspect.schema_cache, _write_cached_schema.__name__, write_mock)
    run = MagicMock(exit_code=0)
    run.parse_output = MagicMock(return_value=payload)
    monkeypatch.setattr(schema_inspect, _run_and_wait.__name__, MagicMock(return_value=run))
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
    monkeypatch.setattr(
        schema_inspect.executor,
        _executor_init.__name__,
        MagicMock(
            return_value=InitResult(
                exit_code=1,
                attempts_used=1,
                stderr="Error: invalid provider constraint",
            )
        ),
    )
    with pytest.raises(RuntimeError, match="terraform init failed") as exc_info:
        schema_inspect.fetch_providers_schema_json(
            TfDoSettings(),
            local_name="aws",
            source="hashicorp/aws",
            version=">= 1.0",
        )
    assert "Error: invalid provider constraint" in str(exc_info.value)


def test_fetch_providers_schema_json_shell_error_wraps_stderr(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    run = MagicMock(spec=ShellRun)
    run.stderr = "schema cmd failed on stderr"
    err = ShellError(run)
    monkeypatch.setattr(
        schema_inspect.executor, _executor_init.__name__, MagicMock(return_value=MagicMock(exit_code=0))
    )
    monkeypatch.setattr(
        schema_inspect.schema_cache,
        _read_resolved_version_from_lock.__name__,
        lambda **_: "1.0.0",
    )
    monkeypatch.setattr(schema_inspect, _run_and_wait.__name__, MagicMock(side_effect=err))
    with pytest.raises(RuntimeError, match="terraform providers schema failed"):
        schema_inspect.fetch_providers_schema_json(
            TfDoSettings(),
            local_name="aws",
            source="hashicorp/aws",
            version=">= 1.0",
            schema_cache_root=tmp_path,
        )


def test_fetch_providers_schema_json_nonzero_exit_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        schema_inspect.executor, _executor_init.__name__, MagicMock(return_value=MagicMock(exit_code=0))
    )
    monkeypatch.setattr(
        schema_inspect.schema_cache,
        _read_resolved_version_from_lock.__name__,
        lambda **_: "1.0.0",
    )
    run = MagicMock()
    run.exit_code = 3
    run.stderr = "stderr detail"
    monkeypatch.setattr(schema_inspect, _run_and_wait.__name__, MagicMock(return_value=run))
    with pytest.raises(RuntimeError, match="exit 3"):
        schema_inspect.fetch_providers_schema_json(
            TfDoSettings(),
            local_name="aws",
            source="hashicorp/aws",
            version=">= 1.0",
            schema_cache_root=tmp_path,
        )


def test_fetch_use_dev_overrides_false_strips_tf_cli_config_and_uses_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = tmp_path / "user.tfrc"
    cfg.write_text(
        """provider_installation {
  dev_overrides = {
    "hashicorp/aws" = "/plugins"
  }
  direct {}
}
""",
        encoding="utf-8",
    )
    monkeypatch.setenv(tf_cli.TF_CLI_CONFIG_FILE_ENV, str(cfg))
    payload = {"provider_schemas": {}}
    init_mock = MagicMock(return_value=MagicMock(exit_code=0))
    monkeypatch.setattr(schema_inspect.executor, _executor_init.__name__, init_mock)
    monkeypatch.setattr(
        schema_inspect.schema_cache,
        _read_resolved_version_from_lock.__name__,
        lambda **_: "1.0.0",
    )
    try_read = MagicMock(return_value=payload)
    monkeypatch.setattr(schema_inspect.schema_cache, _try_read_cached_schema.__name__, try_read)
    write_mock = MagicMock()
    monkeypatch.setattr(schema_inspect.schema_cache, _write_cached_schema.__name__, write_mock)
    run_mock = MagicMock()
    monkeypatch.setattr(schema_inspect, _run_and_wait.__name__, run_mock)
    out = schema_inspect.fetch_providers_schema_json(
        TfDoSettings(),
        local_name="aws",
        source="hashicorp/aws",
        version=">= 1.0",
        schema_cache_root=tmp_path,
        use_dev_overrides=False,
    )
    assert out.payload is payload
    try_read.assert_called_once()
    write_mock.assert_not_called()
    run_mock.assert_not_called()
    init_env = init_mock.call_args[0][0].env
    assert init_env is not None
    assert tf_cli.TF_CLI_CONFIG_FILE_ENV not in init_env
