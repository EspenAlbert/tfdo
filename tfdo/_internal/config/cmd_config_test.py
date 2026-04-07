from pathlib import Path

from tfdo._internal.config.cmd_config import ConfigShowInput, config_show
from tfdo._internal.config.config_file import CONFIG_FILENAME
from tfdo._internal.settings import InteractiveMode, TfDoSettings


def _settings(tmp_path: Path, work_dir: Path | None = None) -> TfDoSettings:
    return TfDoSettings.for_testing(tmp_path, work_dir=work_dir or tmp_path, interactive=InteractiveMode.ALWAYS)


def test_config_show_no_config(tmp_path: Path):
    result = config_show(ConfigShowInput(settings=_settings(tmp_path)))
    assert result.resolved is None
    assert result.layers == []


def test_config_show_at_repo_root(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / CONFIG_FILENAME).write_text("binary: tofu\ntags:\n  env: dev\n")
    result = config_show(ConfigShowInput(settings=_settings(tmp_path)))
    assert len(result.layers) == 1
    assert result.resolved is not None
    assert result.resolved.binary == "tofu"


def test_config_show_three_level_merge(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / CONFIG_FILENAME).write_text("binary: tofu\ntags:\n  org: acme\n")
    mid = tmp_path / "envs"
    mid.mkdir()
    (mid / CONFIG_FILENAME).write_text("tags:\n  tier: mid\n")
    leaf = mid / "staging"
    leaf.mkdir()
    (leaf / CONFIG_FILENAME).write_text("tags:\n  env: staging\n")
    result = config_show(ConfigShowInput(settings=_settings(tmp_path, work_dir=leaf)))
    assert len(result.layers) == 3
    assert result.resolved is not None
    assert result.resolved.binary == "tofu"
    assert result.resolved.tags == {"org": "acme", "tier": "mid", "env": "staging"}
