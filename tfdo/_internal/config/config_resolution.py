from __future__ import annotations

from pydantic import BaseModel

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
    parent_tags: dict[str, str],
    extra_tags: dict[str, str],
    local_tags: dict[str, str],
) -> dict[str, str]:
    merged = {**parent_tags, **extra_tags, **local_tags}
    return merged


def merge_hook_configs(
    parent: list[HookConfig],
    local: list[HookConfig],
) -> list[HookConfig]:
    combined = [*parent, *local]
    return sorted(combined, key=lambda h: (h.priority, h.name))


def resolve_config(
    parent: TfDoConfig | None,
    local: TfDoConfig | None,
    user_config: TfDoUserConfig,
    settings: TfDoSettings,
    extra_tags: dict[str, str] | None = None,
) -> ResolvedConfig:
    p = parent or TfDoConfig()
    loc = local or TfDoConfig()
    extra = extra_tags or {}

    binary = _first_non_none(loc.binary, p.binary, settings.binary) or DEFAULT_BINARY
    tf_version = _first_non_none(loc.tf_version, p.tf_version, settings.tf_version)
    backend = _first_non_none(loc.backend, p.backend)
    tags_inject = _first_non_none(loc.tags_inject, p.tags_inject) or DEFAULT_TAGS_INJECT

    check_config = _first_non_none(loc.check, p.check, user_config.check) or CheckConfig()

    return ResolvedConfig(
        binary=binary,
        tf_version=tf_version,
        backend=backend,
        tags=merge_tags(p.tags, extra, loc.tags),
        var_files=loc.var_files,
        tags_inject=tags_inject,
        hook_configs=merge_hook_configs(p.hook_configs, loc.hook_configs),
        dependencies=loc.dependencies,
        check=check_config,
    )


def resolve_tflint(
    cli_value: bool | None,
    settings: TfDoSettings,
    local: TfDoConfig | None = None,
    parent: TfDoConfig | None = None,
) -> bool:
    if cli_value is not None:
        return cli_value
    if local and local.check and local.check.tflint:
        return True
    if parent and parent.check and parent.check.tflint:
        return True
    user_config = load_user_config(settings)
    if user_config.check and user_config.check.tflint:
        return True
    return False
