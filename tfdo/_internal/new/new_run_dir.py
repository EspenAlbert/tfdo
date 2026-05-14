from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, NamedTuple

import yaml
from pydantic import BaseModel, Field
from zero_3rdparty.file_utils import ensure_parents_write_text

from tfdo._internal import hcl_roundtrip
from tfdo._internal.config import backend_resolution
from tfdo._internal.config.config_file import load_config
from tfdo._internal.config.config_model import BackendConfig, DependencyRef, LocalBackend, S3Backend, TfDoConfig
from tfdo._internal.config.resolver import ResolvedProvider, resolve_run_dir
from tfdo._internal.hcl_entity_parser import TfOutput, TfVariable, parse_dir_entities
from tfdo._internal.hcl_roundtrip import (
    HclAttrRef,
    HclExpression,
    HclLiteral,
    HclValue,
    HclVarRef,
    update_required_providers,
)
from tfdo._internal.hcl_run_dir_gen import terraform_fmt
from tfdo._internal.models import TfDoBaseInput
from tfdo._internal.run.run_context import RunDirContext

logger = logging.getLogger(__name__)


class AttrPromotion(BaseModel):
    attr_name: str
    tf_var_name: str
    default_value: str


class ModuleRunDirConfig(BaseModel):
    source: str
    label: str
    version: str | None = None
    attrs: dict[str, HclValue] = Field(default_factory=dict)
    tf_var_promotions: list[AttrPromotion] = Field(default_factory=list)
    exposed_outputs: list[str] = Field(default_factory=list)


class NewRunDirInput(TfDoBaseInput):
    config: TfDoConfig
    env_name: str
    run_dir_name: str
    module_configs: list[ModuleRunDirConfig] = Field(default_factory=list)
    dependencies: list[DependencyRef] = Field(default_factory=list)


class NewRunDirResult(BaseModel):
    run_dir: Path
    written_paths: list[Path] = Field(default_factory=list)


class ModuleAttrs(NamedTuple):
    required: list[str]
    optional: list[str]


def _module_required_attrs(module_path: Path) -> ModuleAttrs:
    required: list[str] = []
    optional: list[str] = []
    for entity in parse_dir_entities(module_path, recursive=False):
        if isinstance(entity, TfVariable):
            if entity.default is None:
                required.append(entity.name)
            else:
                optional.append(entity.name)
    return ModuleAttrs(sorted(required), sorted(optional))


def _hcl_value_str(value: HclValue) -> str:
    match value:
        case HclLiteral(value=v):
            return f'"{v}"' if isinstance(v, str) else str(v)
        case HclVarRef(path=p) | HclAttrRef(path=p):
            return p
        case HclExpression(expression=e):
            return e
        case list():
            items = ", ".join(_hcl_value_str(item) for item in value)
            return f"[{items}]"
        case dict():
            entries = ", ".join(f"{k} = {_hcl_value_str(v)}" for k, v in value.items())
            return f"{{ {entries} }}"
    return str(value)


def _render_module_call(label: str, source: str, version: str | None, attrs: dict[str, HclValue]) -> str:
    lines = [f'module "{label}" {{', f'  source  = "{source}"']
    if version:
        lines.append(f'  version = "{version}"')
    for name, val in attrs.items():
        lines.append(f"  {name} = {_hcl_value_str(val)}")
    lines.append("}")
    return "\n".join(lines)


def _render_variable(name: str, default: str | None) -> str:
    lines = [f'variable "{name}" {{', "  type = string"]
    if default is not None:
        lines.append(f'  default = "{default}"')
    lines.append("}")
    return "\n".join(lines)


def _render_output(name: str, module_label: str) -> str:
    return "\n".join([f'output "{name}" {{', f"  value = module.{module_label}.{name}", "}"])


def _render_tfvars(promotions: list[AttrPromotion]) -> str:
    return "\n".join(f'{p.attr_name} = "{p.default_value}"' for p in promotions)


def _render_provider_block(name: str) -> str:
    return f'provider "{name}" {{}}'


def _tf_required_version(tf_version: str) -> str:
    parts = tf_version.split(".")
    major_minor = ".".join(parts[:2])
    return f">= {major_minor}"


def _find_backend(work_dir: Path, run_dir: Path) -> BackendConfig | None:
    """Walk work_dir → env dir, returning the most specific backend (child wins)."""
    try:
        rel_parts = run_dir.parent.relative_to(work_dir).parts
    except ValueError:
        return None
    dirs = [work_dir] + [work_dir.joinpath(*rel_parts[: i + 1]) for i in range(len(rel_parts))]
    backend: BackendConfig | None = None
    for d in dirs:
        cfg = load_config(d)
        if cfg and cfg.backend is not None:
            backend = cfg.backend
    return backend


_BACKEND_TF = "backend.tf"


def _write_backend_tf(run_dir: Path, relative: str, backend: BackendConfig, config: TfDoConfig) -> Path:
    ctx = RunDirContext.from_config(relative, config)
    match backend:
        case S3Backend(key=key):
            resolved_key = backend_resolution.resolve_placeholders(key, ctx)
            resolved = backend.model_copy(update={"key": resolved_key})
            hcl_type, hcl_config = "s3", resolved.hcl_config
        case LocalBackend(path=p):
            resolved_path = backend_resolution.resolve_placeholders(p, ctx)
            hcl_type, hcl_config = "local", {"path": f'"{resolved_path}"'}
        case _:
            raise ValueError(f"unsupported backend type: {type(backend)}")
    backend_tf = run_dir / _BACKEND_TF
    original = backend_tf.read_text() if backend_tf.is_file() else ""
    ensure_parents_write_text(backend_tf, hcl_roundtrip.add_backend_block(original, hcl_type, hcl_config))
    return backend_tf


def _provider_attrs(rp: ResolvedProvider) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    if rp.source is not None:
        attrs["source"] = rp.source
    if rp.constraint is not None:
        attrs["version"] = rp.constraint
    return attrs


def new_run_dir(input_model: NewRunDirInput) -> NewRunDirResult:
    settings = input_model.settings
    work_dir = settings.work_dir
    env_name = input_model.env_name
    run_dir_name = input_model.run_dir_name

    relative = input_model.config.run_dir_relative(env_name, run_dir_name)
    run_dir = work_dir / relative
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise ValueError(f"run-dir already exists: {run_dir}")

    written: list[Path] = []

    module_blocks = [_render_module_call(m.label, m.source, m.version, m.attrs) for m in input_model.module_configs]
    main_path = run_dir / "main.tf"
    ensure_parents_write_text(main_path, "\n\n".join(module_blocks))
    written.append(main_path)

    all_promotions = [p for m in input_model.module_configs for p in m.tf_var_promotions]
    dep_var_names = sorted({v for dep in input_model.dependencies for v in dep.outputs.values()})
    promotion_var_names = {p.tf_var_name for p in all_promotions}
    dep_only_vars = [n for n in dep_var_names if n not in promotion_var_names]

    if all_promotions or dep_only_vars:
        var_blocks = [_render_variable(p.tf_var_name, p.default_value) for p in all_promotions]
        var_blocks.extend(_render_variable(name, None) for name in dep_only_vars)
        variables_path = run_dir / "variables.tf"
        ensure_parents_write_text(variables_path, "\n\n".join(var_blocks))
        written.append(variables_path)

    if all_promotions:
        tfvars_path = run_dir / "terraform.tfvars"
        ensure_parents_write_text(tfvars_path, _render_tfvars(all_promotions))
        written.append(tfvars_path)

    output_pairs = [(m.label, name) for m in input_model.module_configs for name in m.exposed_outputs]
    if output_pairs:
        output_blocks = [_render_output(name, label) for label, name in output_pairs]
        outputs_path = run_dir / "outputs.tf"
        ensure_parents_write_text(outputs_path, "\n\n".join(output_blocks))
        written.append(outputs_path)

    resolved = resolve_run_dir(work_dir, relative, settings=settings)
    tf_version = input_model.config.tf_version
    req_version = _tf_required_version(tf_version) if tf_version else None
    if resolved.required_providers or req_version:
        providers_dict = {rp.name: _provider_attrs(rp) for rp in resolved.required_providers}
        versions_path = run_dir / "versions.tf"
        ensure_parents_write_text(
            versions_path, update_required_providers("", providers_dict, required_version=req_version)
        )
        written.append(versions_path)

    if resolved.required_providers:
        provider_blocks = [_render_provider_block(rp.name) for rp in resolved.required_providers]
        providers_path = run_dir / "providers.tf"
        ensure_parents_write_text(providers_path, "\n\n".join(provider_blocks) + "\n")
        written.append(providers_path)

    backend = _find_backend(work_dir, run_dir)
    if backend:
        written.append(_write_backend_tf(run_dir, relative, backend, input_model.config))

    if input_model.dependencies:
        dep_data = {"dependencies": [d.model_dump(exclude_defaults=True) for d in input_model.dependencies]}
        dep_path = run_dir / "tfdo.yaml"
        ensure_parents_write_text(dep_path, yaml.dump(dep_data, default_flow_style=False))
        written.append(dep_path)

    terraform_fmt(run_dir, settings.binary)

    return NewRunDirResult(run_dir=run_dir, written_paths=written)


def module_outputs(module_path: Path) -> list[str]:
    return [e.name for e in parse_dir_entities(module_path, recursive=False) if isinstance(e, TfOutput)]
