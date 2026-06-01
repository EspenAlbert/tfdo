from __future__ import annotations

import logging
from pathlib import Path
from typing import NamedTuple

import yaml
from model_lib import dump as model_dump
from model_lib.serialize.parse import parse_dict
from zero_3rdparty.file_utils import ensure_parents_write_text, find_repo_root

from tfdo._internal.config.config_model import TfDoConfig
from tfdo._internal.settings import TfDoSettings

logger = logging.getLogger(__name__)

CONFIG_FILENAME = "tfdo.yaml"
DEFAULT_TFVARS_FILENAME = "terraform.tfvars"


def save_config(work_dir: Path, config: TfDoConfig) -> Path:
    config_path = work_dir / CONFIG_FILENAME
    data = config.model_dump(mode="json", exclude_none=True)
    ensure_parents_write_text(config_path, model_dump.dump_as_str(data, "yaml"))
    return config_path


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


def resolve_orchestration_root(work_dir: Path) -> Path:
    layers = load_config_layers(work_dir)
    if not layers:
        raise ValueError(f"no tfdo.yaml found at or above {work_dir}")
    for layer in reversed(layers):
        if layer.config.run_dir_discovery:
            return layer.path.parent
    raise ValueError("root tfdo.yaml must define run_dir_discovery pattern")


def root_tfdo_config(work_dir: Path) -> TfDoConfig | None:
    work_dir = work_dir.resolve()
    layers = load_config_layers(work_dir)
    return layers[-1].config if layers else None


def resolve_run_context_label(work_dir: Path) -> str:
    work_dir = work_dir.resolve()
    try:
        repo_root = find_repo_root(work_dir)
    except ValueError:
        return _fallback_run_context_label(work_dir)
    rel = str(work_dir.relative_to(repo_root))
    config = root_tfdo_config(repo_root)
    if config is None:
        return rel
    return config.run_context_label(repo_root, work_dir)


def _fallback_run_context_label(work_dir: Path) -> str:
    cwd = work_dir.resolve()
    if cwd.parents:
        return f"{cwd.parent.name}/{cwd.name}"
    return cwd.name


def resolve_var_file_paths(work_dir: Path, include_default_tfvars: bool = True) -> list[Path]:
    paths: list[Path] = [work_dir / DEFAULT_TFVARS_FILENAME] if include_default_tfvars else []
    for layer in reversed(load_config_layers(work_dir)):
        for var_file in layer.config.var_files:
            path = Path(var_file)
            if not path.is_absolute():
                path = layer.path.parent / path
            paths.append(path)
    return list(dict.fromkeys(paths))


def resolve_env_var_file_names(work_dir: Path) -> list[str]:
    env_file_names: list[str] = []
    for layer in reversed(load_config_layers(work_dir)):
        env_file_names.extend(layer.config.env_var_files)
    return env_file_names


def load_optional_env_vars_from_files(
    work_dir: Path,
    settings: TfDoSettings,
    *,
    log: logging.Logger | None = None,
) -> dict[str, str]:
    active_log = log or logger
    env_file_names = resolve_env_var_file_names(work_dir)
    env_dirs = settings.resolve_env_vars_dirs()
    loaded: dict[str, str] = {}
    for env_file_name in env_file_names:
        env_file_path = next(
            (directory / env_file_name for directory in env_dirs if (directory / env_file_name).is_file()), None
        )
        if env_file_path is None:
            active_log.warning(f"env-var file not found while checking tfvars: {env_file_name}")
            continue
        try:
            file_values = {key: str(value) for key, value in parse_dict(env_file_path).items()}
        except Exception as exc:
            active_log.warning(f"failed to parse env-var file {env_file_path}: {exc}")
            continue
        loaded.update(file_values)
    return loaded
