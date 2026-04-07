from pathlib import Path

import pytest
from pydantic import ValidationError

from tfdo._internal.config.config_file import CONFIG_FILENAME, load_config, load_config_layers


def test_load_config_missing_file(tmp_path: Path):
    assert load_config(tmp_path) is None


def test_load_config_valid_yaml(tmp_path: Path):
    (tmp_path / CONFIG_FILENAME).write_text("binary: tofu\ntags:\n  env: dev\n")
    cfg = load_config(tmp_path)
    assert cfg is not None
    assert cfg.binary == "tofu"
    assert cfg.tags == {"env": "dev"}


def test_load_config_invalid_raises(tmp_path: Path):
    (tmp_path / CONFIG_FILENAME).write_text("backend:\n  type: s3\n")
    with pytest.raises(ValidationError, match="bucket"):
        load_config(tmp_path)


def test_load_config_layers_walks_to_repo_root(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / CONFIG_FILENAME).write_text("binary: tofu\n")
    mid = tmp_path / "envs"
    mid.mkdir()
    (mid / CONFIG_FILENAME).write_text("tags:\n  tier: mid\n")
    leaf = mid / "staging"
    leaf.mkdir()
    (leaf / CONFIG_FILENAME).write_text("tags:\n  env: staging\n")
    layers = load_config_layers(leaf)
    assert len(layers) == 3
    assert layers[0].config.tags == {"env": "staging"}
    assert layers[1].config.tags == {"tier": "mid"}
    assert layers[2].config.binary == "tofu"


def test_load_config_layers_skips_dirs_without_config(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / CONFIG_FILENAME).write_text("binary: tofu\n")
    leaf = tmp_path / "a" / "b"
    leaf.mkdir(parents=True)
    (leaf / CONFIG_FILENAME).write_text("tags:\n  env: dev\n")
    layers = load_config_layers(leaf)
    assert len(layers) == 2
    assert layers[0].path == leaf / CONFIG_FILENAME
    assert layers[1].path == tmp_path / CONFIG_FILENAME


def test_load_config_layers_no_git_repo(tmp_path: Path):
    (tmp_path / CONFIG_FILENAME).write_text("binary: tofu\n")
    layers = load_config_layers(tmp_path)
    assert len(layers) == 1
    assert layers[0].config.binary == "tofu"


def test_load_config_layers_empty(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    assert load_config_layers(tmp_path) == []
