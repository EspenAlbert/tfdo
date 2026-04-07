from __future__ import annotations

import logging
from pathlib import Path

import typer
import yaml
from pydantic import BaseModel
from zero_3rdparty.file_utils import find_repo_root

from tfdo._internal.config import config_file
from tfdo._internal.config.config_model import TfDoConfig
from tfdo._internal.config.config_resolution import ResolvedConfig, resolve_config
from tfdo._internal.models import TfDoBaseInput
from tfdo._internal.settings import load_user_config
from tfdo._internal.typer_app import app, get_settings

logger = logging.getLogger(__name__)

config_app = typer.Typer(help="Configuration management")
app.add_typer(config_app, name="config")


class ConfigShowInput(TfDoBaseInput):
    pass


class ConfigShowResult(BaseModel):
    parent_config_path: Path | None = None
    local_config_path: Path | None = None
    resolved: ResolvedConfig | None = None
    parent: TfDoConfig | None = None
    local: TfDoConfig | None = None


def config_show(input_model: ConfigShowInput) -> ConfigShowResult:
    work_dir = input_model.settings.work_dir.resolve()
    try:
        repo_root = find_repo_root(work_dir)
    except ValueError:
        repo_root = None

    parent: TfDoConfig | None = None
    parent_path: Path | None = None
    local: TfDoConfig | None = None
    local_path: Path | None = None

    local = config_file.load_config(work_dir)
    if local is not None:
        local_path = work_dir / config_file.CONFIG_FILENAME

    if repo_root and repo_root != work_dir:
        parent = config_file.load_config(repo_root)
        if parent is not None:
            parent_path = repo_root / config_file.CONFIG_FILENAME

    if local is None and parent is None:
        return ConfigShowResult()

    user_config = load_user_config(input_model.settings)
    resolved = resolve_config(parent, local, user_config, input_model.settings)

    return ConfigShowResult(
        parent_config_path=parent_path,
        local_config_path=local_path,
        resolved=resolved,
        parent=parent,
        local=local,
    )


@config_app.command("show")
def show_cmd(ctx: typer.Context) -> None:
    """Print resolved tfdo.yaml config for current directory."""
    settings = get_settings(ctx)
    result = config_show(ConfigShowInput(settings=settings))
    if result.resolved is None:
        logger.info("no tfdo.yaml found")
        return
    if result.parent_config_path:
        logger.info(f"parent: {result.parent_config_path}")
    if result.local_config_path:
        logger.info(f"local:  {result.local_config_path}")
    resolved_dict = result.resolved.model_dump(mode="json")
    logger.info(f"resolved config:\n{yaml.dump(resolved_dict, default_flow_style=False)}")
