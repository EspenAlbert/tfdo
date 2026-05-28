from pathlib import Path

from tfdo._internal.core import lifecycle_env
from tfdo._internal.output import plan_artifacts


def test_lifecycle_env_sets_debug_path_and_default_log_level(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TF_LOG", raising=False)
    env = lifecycle_env.lifecycle_env(tmp_path)
    assert env["TF_LOG"] == "DEBUG"
    assert env["TF_LOG_PATH"] == str(plan_artifacts.debug_log_path(tmp_path).resolve())


def test_lifecycle_env_respects_existing_tf_log(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TF_LOG", "TRACE")
    env = lifecycle_env.lifecycle_env(tmp_path)
    assert env["TF_LOG"] == "TRACE"


def test_lifecycle_env_respects_existing_tf_log_path(tmp_path: Path, monkeypatch) -> None:
    custom_path = tmp_path / "custom-debug.log"
    monkeypatch.setenv("TF_LOG_PATH", str(custom_path))
    env = lifecycle_env.lifecycle_env(tmp_path)
    assert env["TF_LOG_PATH"] == str(custom_path)


def test_resolved_debug_log_path_uses_env_override(tmp_path: Path, monkeypatch) -> None:
    custom_path = tmp_path / "custom-debug.log"
    monkeypatch.setenv("TF_LOG_PATH", str(custom_path))
    assert lifecycle_env.resolved_debug_log_path(tmp_path) == custom_path.resolve()


def test_resolved_debug_log_path_defaults_to_tfdo_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TF_LOG_PATH", raising=False)
    assert lifecycle_env.resolved_debug_log_path(tmp_path) == plan_artifacts.debug_log_path(tmp_path).resolve()


def test_begin_lifecycle_debug_log_archives_previous(tmp_path: Path) -> None:
    log_path = plan_artifacts.debug_log_path(tmp_path)
    log_path.parent.mkdir(parents=True)
    log_path.write_text("old run")
    plan_artifacts.begin_lifecycle_debug_log(tmp_path)
    archived = plan_artifacts.tfdo_dir(tmp_path) / "debug_old" / "01_debug.log"
    assert archived.read_text() == "old run"
    assert not log_path.is_file()
