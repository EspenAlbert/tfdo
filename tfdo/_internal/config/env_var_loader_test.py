from __future__ import annotations

import os
from pathlib import Path

import pytest

from tfdo._internal.config.config_model import TfDoConfig
from tfdo._internal.config.env_var_loader import (
    ENV_VARS_DIRS_KEY,
    ENV_VARS_LOAD_KEY,
    EnvVarMissingError,
    load_env_vars,
)
from tfdo._internal.settings import TfDoSettings


@pytest.fixture()
def settings(tmp_path: Path) -> TfDoSettings:
    return TfDoSettings.for_testing(tmp_path)


@pytest.fixture()
def env_dir(settings: TfDoSettings) -> Path:
    d = settings.static_root / "env_vars"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _config(*files: str) -> TfDoConfig:
    return TfDoConfig(env_var_files=list(files))


def test_auto_non_ci_loads(env_dir: Path, settings: TfDoSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    (env_dir / "creds.yaml").write_text("MY_KEY: my-value\n")
    monkeypatch.delenv("MY_KEY", raising=False)

    result = load_env_vars(_config("creds.yaml"), settings, {})

    assert result.merged == {"MY_KEY": "my-value"}
    assert result.reason == "loaded"
    assert len(result.loaded_paths) == 1
    assert os.environ.get("MY_KEY") == "my-value"


def test_auto_ci_skips(env_dir: Path, settings: TfDoSettings) -> None:
    (env_dir / "creds.yaml").write_text("MY_KEY: my-value\n")

    result = load_env_vars(_config("creds.yaml"), settings, {"CI": "true"})

    assert result.merged == {}
    assert result.reason == "skip: CI detected"
    assert result.loaded_paths == []


def test_force_load_in_ci(env_dir: Path, settings: TfDoSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    (env_dir / "creds.yaml").write_text("FORCE_KEY: force-value\n")
    monkeypatch.delenv("FORCE_KEY", raising=False)

    result = load_env_vars(_config("creds.yaml"), settings, {"CI": "true", ENV_VARS_LOAD_KEY: "load"})

    assert result.merged == {"FORCE_KEY": "force-value"}
    assert result.reason == "load: forced"


def test_force_skip(env_dir: Path, settings: TfDoSettings) -> None:
    (env_dir / "creds.yaml").write_text("SKIP_KEY: skip-value\n")

    result = load_env_vars(_config("creds.yaml"), settings, {ENV_VARS_LOAD_KEY: "skip"})

    assert result.merged == {}
    assert result.reason == "skip: forced"


def test_missing_file_raises(settings: TfDoSettings) -> None:
    with pytest.raises(EnvVarMissingError) as exc_info:
        load_env_vars(_config("missing.yaml"), settings, {})

    err = exc_info.value
    assert err.filename == "missing.yaml"
    assert len(err.search_dirs) == 1


def test_later_file_wins_on_collision(env_dir: Path, settings: TfDoSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    (env_dir / "first.yaml").write_text("SHARED_KEY: first-value\n")
    (env_dir / "second.yaml").write_text("SHARED_KEY: second-value\n")
    monkeypatch.delenv("SHARED_KEY", raising=False)

    result = load_env_vars(_config("first.yaml", "second.yaml"), settings, {})

    assert result.merged["SHARED_KEY"] == "second-value"


def test_env_format_parsed(env_dir: Path, settings: TfDoSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    (env_dir / "creds.env").write_text('ENV_KEY="env-value"\n# comment\nOTHER=plain\n')
    monkeypatch.delenv("ENV_KEY", raising=False)
    monkeypatch.delenv("OTHER", raising=False)

    result = load_env_vars(_config("creds.env"), settings, {})

    assert result.merged == {"ENV_KEY": "env-value", "OTHER": "plain"}


def test_custom_dirs_override(tmp_path: Path, settings: TfDoSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    custom_dir = tmp_path / "custom"
    custom_dir.mkdir()
    (custom_dir / "creds.yaml").write_text("CUSTOM_KEY: custom-value\n")
    monkeypatch.delenv("CUSTOM_KEY", raising=False)

    result = load_env_vars(_config("creds.yaml"), settings, {ENV_VARS_DIRS_KEY: str(custom_dir)})

    assert result.merged == {"CUSTOM_KEY": "custom-value"}
