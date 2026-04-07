from pathlib import Path

import pytest
from pydantic import ValidationError

from tfdo._internal.config import config_file
from tfdo._internal.config.config_file import load_config


def test_load_config_missing_file(tmp_path: Path):
    assert load_config(tmp_path) is None


def test_load_config_valid_yaml(tmp_path: Path):
    (tmp_path / config_file.CONFIG_FILENAME).write_text("binary: tofu\ntags:\n  env: dev\n")
    cfg = load_config(tmp_path)
    assert cfg is not None
    assert cfg.binary == "tofu"
    assert cfg.tags == {"env": "dev"}


def test_load_config_invalid_raises(tmp_path: Path):
    (tmp_path / config_file.CONFIG_FILENAME).write_text("backend:\n  type: s3\n")
    with pytest.raises(ValidationError, match="bucket"):
        load_config(tmp_path)
