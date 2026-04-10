from __future__ import annotations

import logging

import typer
import yaml
from pydantic import BaseModel

from tfdo._internal.config.config_file import ConfigLayer, load_config_layers
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
    layers: list[ConfigLayer] = []
    resolved: ResolvedConfig | None = None


def config_show(input_model: ConfigShowInput) -> ConfigShowResult:
    layers = load_config_layers(input_model.settings.work_dir)
    if not layers:
        return ConfigShowResult()

    user_config = load_user_config(input_model.settings)
    resolved = resolve_config(layers, user_config, input_model.settings)
    return ConfigShowResult(layers=layers, resolved=resolved)


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
