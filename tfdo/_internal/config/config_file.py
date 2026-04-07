from __future__ import annotations

import logging
from pathlib import Path
from typing import NamedTuple

import yaml
from zero_3rdparty.file_utils import find_repo_root

from tfdo._internal.config.config_model import TfDoConfig

logger = logging.getLogger(__name__)

CONFIG_FILENAME = "tfdo.yaml"


def load_config(dir_path: Path) -> TfDoConfig | None:
    config_path = dir_path / CONFIG_FILENAME
    if not config_path.is_file():
        return None
    data = yaml.safe_load(config_path.read_text()) or {}
    return TfDoConfig(**data)


class ConfigLayer(NamedTuple):
    config: TfDoConfig
    path: Path


def load_config_layers(work_dir: Path) -> list[ConfigLayer]:
    work_dir = work_dir.resolve()
    try:
        repo_root = find_repo_root(work_dir)
    except ValueError:
        cfg = load_config(work_dir)
        if cfg:
            return [ConfigLayer(cfg, work_dir / CONFIG_FILENAME)]
        return []

    layers: list[ConfigLayer] = []
    current = work_dir
    while True:
        if cfg := load_config(current):
            layers.append(ConfigLayer(cfg, current / CONFIG_FILENAME))
        if current == repo_root:
            break
        current = current.parent
    return layers
