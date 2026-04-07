from __future__ import annotations

from pydantic import BaseModel

from tfdo._internal.config.config_file import ConfigLayer
from tfdo._internal.config.config_model import (
    BackendDefaults,
    DependencyRef,
    HookConfig,
    TfDoConfig,
)
from tfdo._internal.settings import CheckConfig, TfDoSettings, TfDoUserConfig, load_user_config

DEFAULT_BINARY = "terraform"
DEFAULT_TAGS_INJECT = False


class ResolvedConfig(BaseModel):
    binary: str
    tf_version: str | None
    backend: BackendDefaults | None
    tags: dict[str, str]
    var_files: list[str]
    tags_inject: bool
    hook_configs: list[HookConfig]
    dependencies: list[DependencyRef]
    check: CheckConfig


def _first_non_none(*values):
    for v in values:
        if v is not None:
            return v
    return None


def merge_tags(
    layer_tags: list[dict[str, str]],
    extra_tags: dict[str, str],
) -> dict[str, str]:
    merged: dict[str, str] = {}
    for tags in reversed(layer_tags):
        merged.update(tags)
    merged.update(extra_tags)
    if layer_tags:
        merged.update(layer_tags[0])
    return merged


def merge_hook_configs(layers: list[list[HookConfig]]) -> list[HookConfig]:
    combined = [h for layer_hooks in layers for h in layer_hooks]
    return sorted(combined, key=lambda h: (h.priority, h.name))


def resolve_config(
    layers: list[ConfigLayer],
    user_config: TfDoUserConfig,
    settings: TfDoSettings,
    extra_tags: dict[str, str] | None = None,
) -> ResolvedConfig:
    configs = [layer.config for layer in layers] if layers else [TfDoConfig()]
    extra = extra_tags or {}
    local = configs[0]

    scalar_values = [c.binary for c in configs]
    binary = _first_non_none(*scalar_values, settings.binary) or DEFAULT_BINARY
    tf_version = _first_non_none(*(c.tf_version for c in configs), settings.tf_version)
    backend = _first_non_none(*(c.backend for c in configs))
    tags_inject = _first_non_none(*(c.tags_inject for c in configs)) or DEFAULT_TAGS_INJECT
    check_config = _first_non_none(*(c.check for c in configs), user_config.check) or CheckConfig()

    return ResolvedConfig(
        binary=binary,
        tf_version=tf_version,
        backend=backend,
        tags=merge_tags([c.tags for c in configs], extra),
        var_files=local.var_files,
        tags_inject=tags_inject,
        hook_configs=merge_hook_configs([c.hook_configs for c in configs]),
        dependencies=local.dependencies,
        check=check_config,
    )


def resolve_tflint(
    cli_value: bool | None,
    settings: TfDoSettings,
    layers: list[ConfigLayer] | None = None,
) -> bool:
    if cli_value is not None:
        return cli_value
    for layer in layers or []:
        if layer.config.check and layer.config.check.tflint:
            return True
    user_config = load_user_config(settings)
    if user_config.check and user_config.check.tflint:
        return True
    return False
