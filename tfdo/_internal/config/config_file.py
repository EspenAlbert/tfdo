from __future__ import annotations

import logging
from pathlib import Path

import yaml

from tfdo._internal.config.config_model import TfDoConfig

logger = logging.getLogger(__name__)

CONFIG_FILENAME = "tfdo.yaml"


def load_config(dir_path: Path) -> TfDoConfig | None:
    config_path = dir_path / CONFIG_FILENAME
    if not config_path.is_file():
        return None
    data = yaml.safe_load(config_path.read_text()) or {}
    return TfDoConfig(**data)
