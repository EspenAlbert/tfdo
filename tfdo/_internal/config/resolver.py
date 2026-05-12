from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel

from tfdo._internal.config.config_file import load_config
from tfdo._internal.config.config_model import (
    ProviderConstraint,
    TfDoConfig,
    merge_env_var_files,
    merge_modules,
    merge_providers,
)
from tfdo._internal.config.env_var_loader import LoadResult, load_env_vars
from tfdo._internal.config.provider_hints import ProviderHints, load_provider_hints
from tfdo._internal.core import executor
from tfdo._internal.hcl_entity_parser import (
    TfModuleCall,
    TfRequiredProviders,
    parse_dir_entities,
)
from tfdo._internal.models import InitInput
from tfdo._internal.settings import TfDoSettings

_LOCAL_PREFIXES = ("./", "../", "/")
_REGISTRY_RE = re.compile(r"^[^/]+/[^/]+/[^/]+$")

_init_cache: set[Path] = set()


class UnsupportedModuleSourceError(ValueError):
    def __init__(self, source: str) -> None:
        super().__init__(f"unsupported module source: {source!r}")
        self.source = source


class ResolvedProvider(BaseModel):
    name: str
    source: str | None = None
    constraint: str | None = None
    is_declared_in_hcl: bool = False
    is_declared_in_tfdo_yaml: bool = False
    has_hints_entry: bool = False
    is_force_injected: bool = False


class ResolvedModule(BaseModel):
    source: str
    constraint: str | None = None


class ResolvedRunDirConfig(BaseModel):
    required_providers: list[ResolvedProvider]
    resolved_modules: list[ResolvedModule]
    provider_hints: dict[str, ProviderHints]
    auth_variables: list[tuple[str, str]]
    loaded_env_vars: LoadResult


def _is_local(source: str) -> bool:
    return any(source.startswith(p) for p in _LOCAL_PREFIXES)


def _is_registry(source: str) -> bool:
    return bool(_REGISTRY_RE.match(source))


def _load_cfg(dir_path: Path) -> TfDoConfig:
    return load_config(dir_path) or TfDoConfig()


def _run_init(run_dir: Path, settings: TfDoSettings) -> None:
    resolved = run_dir.resolve()
    if resolved in _init_cache:
        return
    result = executor.init(
        InitInput(
            settings=settings.with_work_dir(resolved),
            extra_args=["-input=false", "-no-color"],
        )
    )
    if result.exit_code != 0:
        raise RuntimeError(f"terraform init failed in {resolved}: {result.stderr}")
    _init_cache.add(resolved)


def _providers_from_module(call: TfModuleCall, run_dir: Path, settings: TfDoSettings) -> list[str]:
    source = call.source
    if _is_local(source):
        module_path = (run_dir / source).resolve()
    elif _is_registry(source):
        modules_dir = run_dir / ".terraform" / "modules" / call.name
        if not modules_dir.exists():
            _run_init(run_dir, settings)
        module_path = modules_dir
    else:
        raise UnsupportedModuleSourceError(source)
    if not module_path.exists():
        return []
    names: list[str] = []
    for entity in parse_dir_entities(module_path):
        if isinstance(entity, TfRequiredProviders):
            names.extend(p.name for p in entity.providers)
    return names


def resolve_run_dir(
    fixture_path: Path,
    env: str,
    run_dir_relative_path: str,
    *,
    settings: TfDoSettings | None = None,
    os_env: Mapping[str, str] | None = None,
) -> ResolvedRunDirConfig:
    _os_env: Mapping[str, str] = os_env if os_env is not None else os.environ
    _settings = settings or TfDoSettings()

    root_cfg = _load_cfg(fixture_path)
    env_cfg = _load_cfg(fixture_path / "envs" / env)
    run_dir = fixture_path / run_dir_relative_path
    run_dir_cfg = _load_cfg(run_dir)

    hints_registry = load_provider_hints(fixture_path / "provider_hints.yaml")

    provider_pool = {p.name: p for p in merge_providers([root_cfg, env_cfg], run_dir_cfg)}
    module_pool = {m.source: m for m in merge_modules([root_cfg, env_cfg], run_dir_cfg)}

    all_env_files = merge_env_var_files([root_cfg, env_cfg], run_dir_cfg)
    loaded = load_env_vars(TfDoConfig(env_var_files=all_env_files), _settings, _os_env)

    entities = parse_dir_entities(run_dir)

    hcl_names: set[str] = set()
    for e in entities:
        if isinstance(e, TfRequiredProviders):
            hcl_names.update(p.name for p in e.providers)

    module_calls = [e for e in entities if isinstance(e, TfModuleCall)]
    module_provider_names: set[str] = set()
    resolved_modules: list[ResolvedModule] = []
    for call in module_calls:
        module_provider_names.update(_providers_from_module(call, run_dir, _settings))
        if _is_registry(call.source):
            mc = module_pool.get(call.source)
            constraint = mc.constraint if mc else call.version
            resolved_modules.append(ResolvedModule(source=call.source, constraint=constraint))

    force_inject = {p.name for p in run_dir_cfg.providers}

    tfdo_yaml_names: set[str] = set()
    for cfg in [root_cfg, env_cfg, run_dir_cfg]:
        tfdo_yaml_names.update(p.name for p in cfg.providers)

    all_names = hcl_names | module_provider_names | force_inject
    required_providers, hints_by_provider, auth_variables = _build_providers(
        all_names, provider_pool, hints_registry, force_inject, hcl_names, tfdo_yaml_names
    )

    return ResolvedRunDirConfig(
        required_providers=required_providers,
        resolved_modules=resolved_modules,
        provider_hints=hints_by_provider,
        auth_variables=auth_variables,
        loaded_env_vars=loaded,
    )


def _build_providers(
    all_names: set[str],
    provider_pool: dict[str, ProviderConstraint],
    hints_registry: dict[str, ProviderHints],
    force_inject: set[str],
    hcl_names: set[str],
    tfdo_yaml_names: set[str],
) -> tuple[list[ResolvedProvider], dict[str, ProviderHints], list[tuple[str, str]]]:
    required_providers: list[ResolvedProvider] = []
    hints_by_provider: dict[str, ProviderHints] = {}
    auth_variables: list[tuple[str, str]] = []
    seen_auth_vars: set[str] = set()

    for name in sorted(all_names):
        pc = provider_pool.get(name)
        hints = hints_registry.get(name)

        if hints is not None:
            source = hints.source
            hints_by_provider[name] = hints
            for vm in hints.auth_variables:
                if vm.env not in seen_auth_vars:
                    auth_variables.append((vm.env, vm.tf_var))
                    seen_auth_vars.add(vm.env)
        elif name in force_inject:
            source = f"hashicorp/{name}"
        else:
            source = None

        constraint = pc.constraint if pc is not None else None
        required_providers.append(
            ResolvedProvider(
                name=name,
                source=source,
                constraint=constraint,
                is_declared_in_hcl=name in hcl_names,
                is_declared_in_tfdo_yaml=name in tfdo_yaml_names,
                has_hints_entry=hints is not None,
                is_force_injected=name in force_inject,
            )
        )

    return required_providers, hints_by_provider, auth_variables
