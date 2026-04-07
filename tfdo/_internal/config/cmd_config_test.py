from pathlib import Path

from tfdo._internal.config import config_file
from tfdo._internal.config.cmd_config import ConfigShowInput, config_show
from tfdo._internal.settings import InteractiveMode, TfDoSettings


def _settings(tmp_path: Path) -> TfDoSettings:
    return TfDoSettings.for_testing(tmp_path, work_dir=tmp_path, interactive=InteractiveMode.ALWAYS)


def test_config_show_no_config(tmp_path: Path):
    result = config_show(ConfigShowInput(settings=_settings(tmp_path)))
    assert result.resolved is None
    assert result.local is None
    assert result.parent is None


def test_config_show_at_repo_root(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / config_file.CONFIG_FILENAME).write_text("binary: tofu\ntags:\n  env: dev\n")
    result = config_show(ConfigShowInput(settings=_settings(tmp_path)))
    assert result.local is not None
    assert result.parent is None
    assert result.resolved is not None
    assert result.resolved.binary == "tofu"


def test_config_show_subdirectory_merges(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / config_file.CONFIG_FILENAME).write_text("binary: tofu\ntags:\n  env: prod\n")
    child = tmp_path / "envs" / "staging"
    child.mkdir(parents=True)
    (child / config_file.CONFIG_FILENAME).write_text("tags:\n  env: staging\n  team: infra\n")
    settings = TfDoSettings.for_testing(tmp_path, work_dir=child, interactive=InteractiveMode.ALWAYS)
    result = config_show(ConfigShowInput(settings=settings))
    assert result.parent is not None
    assert result.parent.binary == "tofu"
    assert result.local is not None
    assert result.resolved is not None
    assert result.resolved.binary == "tofu"
    assert result.resolved.tags == {"env": "staging", "team": "infra"}
