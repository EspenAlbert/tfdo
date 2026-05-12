from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

from model_lib.serialize.parse import parse_dict

from tfdo._internal.config.config_model import TfDoConfig, merge_env_var_files
from tfdo._internal.config.enums import EnvVarLoadMode
from tfdo._internal.settings import TfDoSettings

ENV_VARS_LOAD_KEY = "TFDO_ENV_VARS_LOAD"
ENV_VARS_DIRS_KEY = "TFDO_ENV_VARS_DIRS"
_ENV_VARS_SUBDIR = "env_vars"


class EnvVarMissingError(Exception):
    def __init__(self, filename: str, search_dirs: list[Path]) -> None:
        dirs_str = ", ".join(str(d) for d in search_dirs)
        super().__init__(f"env-var file '{filename}' not found in: {dirs_str}")
        self.filename = filename
        self.search_dirs = search_dirs


class LoadResult(NamedTuple):
    merged: dict[str, str]
    loaded_paths: list[Path]
    reason: str


def _search_dirs(env: Mapping[str, str], settings: TfDoSettings) -> list[Path]:
    raw = env.get(ENV_VARS_DIRS_KEY)
    if raw:
        return [Path(p) for p in raw.split(":")]
    return [settings.static_root / _ENV_VARS_SUBDIR]


def _resolve_file(name: str, dirs: list[Path]) -> Path:
    for d in dirs:
        candidate = d / name
        if candidate.is_file():
            return candidate
    raise EnvVarMissingError(name, dirs)


def _parse_file(path: Path) -> dict[str, str]:
    return {k: str(v) for k, v in parse_dict(path).items()}


def load_env_vars(
    config: TfDoConfig,
    settings: TfDoSettings,
    env: Mapping[str, str],
) -> LoadResult:
    mode = EnvVarLoadMode(env.get(ENV_VARS_LOAD_KEY, EnvVarLoadMode.auto))

    if mode == EnvVarLoadMode.skip:
        return LoadResult(merged={}, loaded_paths=[], reason="skip: forced")
    if mode == EnvVarLoadMode.auto and env.get("CI") == "true":
        return LoadResult(merged={}, loaded_paths=[], reason="skip: CI detected")

    files = merge_env_var_files([], config)
    dirs = _search_dirs(env, settings)
    merged: dict[str, str] = {}
    loaded_paths: list[Path] = []

    for name in files:
        path = _resolve_file(name, dirs)
        merged.update(_parse_file(path))
        loaded_paths.append(path)

    os.environ.update(merged)
    reason = "load: forced" if mode == EnvVarLoadMode.load else "loaded"
    return LoadResult(merged=merged, loaded_paths=loaded_paths, reason=reason)
