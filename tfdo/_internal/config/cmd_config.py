from __future__ import annotations

import logging

import typer
import yaml
from pydantic import BaseModel, Field
from zero_3rdparty.file_utils import ensure_parents_write_text, find_repo_root

from tfdo._internal.config.config_file import ConfigLayer, load_config_layers
from tfdo._internal.config.config_resolution import ResolvedConfig, resolve_config
from tfdo._internal.config.scan import ScanResult, scan_for_run_dirs
from tfdo._internal.models import TfDoBaseInput
from tfdo._internal.settings import load_user_config
from tfdo._internal.typer_app import app, get_settings

logger = logging.getLogger(__name__)

config_app = typer.Typer(help="Configuration management")
app.add_typer(config_app, name="config")


class ConfigShowInput(TfDoBaseInput):
    pass


class ConfigShowResult(BaseModel):
    layers: list[ConfigLayer] = Field(default_factory=list)
    resolved: ResolvedConfig | None = None


def config_show(input_model: ConfigShowInput) -> ConfigShowResult:
    layers = load_config_layers(input_model.settings.work_dir)
    if not layers:
        return ConfigShowResult()

    user_config = load_user_config(input_model.settings)
    resolved = resolve_config(layers, user_config, input_model.settings)
    return ConfigShowResult(layers=layers, resolved=resolved)


class ConfigInitInput(TfDoBaseInput):
    dry_run: bool = False


def config_init(input_model: ConfigInitInput) -> ScanResult:
    repo_root = find_repo_root(input_model.settings.work_dir)
    result = scan_for_run_dirs(repo_root)
    if input_model.dry_run:
        return result
    if result.inferred_pattern:
        config_content = yaml.dump({"run_dir_discovery": result.inferred_pattern}, default_flow_style=False)
        config_path = repo_root / "tfdo.yaml"
        ensure_parents_write_text(config_path, config_content)
        logger.info(f"wrote {config_path}")
    return result


@config_app.command("show")
def show_cmd(ctx: typer.Context) -> None:
    """Print resolved tfdo.yaml config layers and merged result for current work directory."""
    settings = get_settings(ctx)
    result = config_show(ConfigShowInput(settings=settings))
    if result.resolved is None:
        logger.info("no tfdo.yaml found")
        return
    for layer in result.layers:
        logger.info(f"layer: {layer.path}")
    resolved_dict = result.resolved.model_dump(mode="json")
    logger.info(f"resolved config:\n{yaml.dump(resolved_dict, default_flow_style=False)}")


@config_app.command("init")
def init_cmd(
    ctx: typer.Context,
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview detected directories without writing tfdo.yaml"),
) -> None:
    """Detect run directories and generate a starter tfdo.yaml."""
    settings = get_settings(ctx)
    result = config_init(ConfigInitInput(settings=settings, dry_run=dry_run))
    if not result.directories:
        logger.info("no directories with backend blocks found")
        return
    logger.info(f"found {len(result.directories)} run directories:")
    for d in result.directories:
        logger.info(f"  {d}")
    if result.inferred_pattern:
        logger.info(f"inferred pattern: {result.inferred_pattern}")
    else:
        logger.info("could not infer a discovery pattern (directories have different depths)")
