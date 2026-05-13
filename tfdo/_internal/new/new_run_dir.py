from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, NamedTuple

from pydantic import BaseModel, Field
from zero_3rdparty.file_utils import ensure_parents_write_text

from tfdo._internal.config.config_model import TfDoConfig
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


class NewRunDirResult(BaseModel):
    run_dir: Path
    written_paths: list[Path] = Field(default_factory=list)


class ModuleAttrs(NamedTuple):
    required: list[str]
    optional: list[str]


def _module_required_attrs(module_path: Path) -> ModuleAttrs:
    required: list[str] = []
    optional: list[str] = []
    for entity in parse_dir_entities(module_path):
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

    run_dir = work_dir / "envs" / env_name / run_dir_name
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
    if all_promotions:
        var_blocks = [_render_variable(p.tf_var_name, p.default_value) for p in all_promotions]
        variables_path = run_dir / "variables.tf"
        ensure_parents_write_text(variables_path, "\n\n".join(var_blocks))
        written.append(variables_path)

        tfvars_path = run_dir / "terraform.tfvars"
        ensure_parents_write_text(tfvars_path, _render_tfvars(all_promotions))
        written.append(tfvars_path)

    output_pairs = [(m.label, name) for m in input_model.module_configs for name in m.exposed_outputs]
    if output_pairs:
        output_blocks = [_render_output(name, label) for label, name in output_pairs]
        outputs_path = run_dir / "outputs.tf"
        ensure_parents_write_text(outputs_path, "\n\n".join(output_blocks))
        written.append(outputs_path)

    resolved = resolve_run_dir(work_dir, f"envs/{env_name}/{run_dir_name}", settings=settings)
    if resolved.required_providers:
        providers_dict = {rp.name: _provider_attrs(rp) for rp in resolved.required_providers}
        versions_path = run_dir / "versions.tf"
        ensure_parents_write_text(versions_path, update_required_providers("", providers_dict))
        written.append(versions_path)

    terraform_fmt(run_dir, settings.binary)

    return NewRunDirResult(run_dir=run_dir, written_paths=written)


def module_outputs(module_path: Path) -> list[str]:
    return [e.name for e in parse_dir_entities(module_path) if isinstance(e, TfOutput)]
