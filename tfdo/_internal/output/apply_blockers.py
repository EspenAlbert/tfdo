from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from tfdo._internal.output.apply_state import seed_apply_addrs
from tfdo._internal.output.parser import parse_plan_file

_REF_INDEX = re.compile(r"\[[^\]]*\]$")
_SKIP_PREFIXES = ("path.", "local.", "terraform.")


class ConfigExpression(BaseModel):
    model_config = ConfigDict(extra="ignore")

    references: list[str] = Field(default_factory=list)


class ConfigResource(BaseModel):
    model_config = ConfigDict(extra="ignore")

    address: str
    depends_on: list[str] = Field(default_factory=list)
    expressions: dict[str, ConfigExpression] = Field(default_factory=dict)


class ConfigModule(BaseModel):
    model_config = ConfigDict(extra="ignore")

    resources: list[ConfigResource] = Field(default_factory=list)
    module_calls: dict[str, ConfigModuleCall] = Field(default_factory=dict)


class ConfigModuleCall(BaseModel):
    model_config = ConfigDict(extra="ignore")

    depends_on: list[str] = Field(default_factory=list)
    expressions: dict[str, ConfigExpression] = Field(default_factory=dict)
    module: ConfigModule | None = None


class PlanConfiguration(BaseModel):
    model_config = ConfigDict(extra="ignore")

    root_module: ConfigModule | None = None


class PlanWithConfiguration(BaseModel):
    model_config = ConfigDict(extra="ignore")

    configuration: PlanConfiguration | None = None


def build_apply_blockers(plan_path: Path) -> dict[str, frozenset[str]]:
    plan = parse_plan_file(plan_path)
    apply_addrs = frozenset(seed_apply_addrs(plan))
    raw = json.loads(plan_path.read_text())
    wrapper = PlanWithConfiguration.model_validate(raw)
    if wrapper.configuration is None or wrapper.configuration.root_module is None:
        return {}
    if not apply_addrs:
        return {}
    blockers: dict[str, frozenset[str]] = {}
    _walk_module(
        wrapper.configuration.root_module,
        module_path="",
        var_bindings={},
        apply_addrs=apply_addrs,
        blockers=blockers,
    )
    return blockers


def _walk_module(
    module: ConfigModule,
    *,
    module_path: str,
    var_bindings: dict[str, frozenset[str]],
    apply_addrs: frozenset[str],
    blockers: dict[str, frozenset[str]],
) -> None:
    for resource in module.resources:
        cfg_addr = f"{module_path}{resource.address}"
        if cfg_addr not in apply_addrs:
            continue
        refs: set[str] = set(resource.depends_on)
        for expr in resource.expressions.values():
            refs.update(expr.references)
        resolved: set[str] = set()
        for ref in refs:
            resolved |= _resolve_ref(ref, module_path, apply_addrs, var_bindings)
        blockers[cfg_addr] = frozenset(resolved - {cfg_addr})

    for call_name, call in module.module_calls.items():
        child_bindings = _var_bindings_from_call(call, module_path, apply_addrs)
        if call.module is not None:
            _walk_module(
                call.module,
                module_path=f"{module_path}module.{call_name}.",
                var_bindings=child_bindings,
                apply_addrs=apply_addrs,
                blockers=blockers,
            )


def _var_bindings_from_call(
    call: ConfigModuleCall,
    module_path: str,
    apply_addrs: frozenset[str],
) -> dict[str, frozenset[str]]:
    bindings: dict[str, frozenset[str]] = {}
    for input_name, expr in call.expressions.items():
        resolved: set[str] = set()
        for ref in expr.references:
            resolved |= _resolve_ref(ref, module_path, apply_addrs, {})
        bindings[input_name] = frozenset(resolved)
    return bindings


def _resolve_ref(
    ref: str,
    module_path: str,
    apply_addrs: frozenset[str],
    var_bindings: dict[str, frozenset[str]],
) -> frozenset[str]:
    if ref.startswith(_SKIP_PREFIXES):
        return frozenset()
    if ref.startswith("var."):
        var_name = ref.removeprefix("var.").split("[", maxsplit=1)[0]
        return var_bindings.get(var_name, frozenset())
    stripped = _REF_INDEX.sub("", ref)
    if stripped.startswith("data.") and stripped not in apply_addrs:
        return frozenset()
    qualified = stripped if stripped.startswith("module.") else f"{module_path}{stripped}"
    return frozenset(addr for addr in apply_addrs if qualified == addr or qualified.startswith(f"{addr}."))
