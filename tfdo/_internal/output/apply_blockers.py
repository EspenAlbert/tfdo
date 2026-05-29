from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tfdo._internal.output import apply_state, parser

type ExpressionValue = dict[str, Any] | list[dict[str, Any]]
type JsonObject = dict[str, Any]
type JsonValue = JsonObject | list[Any] | str | int | float | bool | None

_REF_INDEX = re.compile(r"\[[^\]]*\]$")
_NORM_INDEX = re.compile(r"\[[^\]]+\]")
_SKIP_PREFIXES = ("path.", "local.", "terraform.")


class ConfigExpression(BaseModel):
    model_config = ConfigDict(extra="ignore")

    references: list[str] = Field(default_factory=list)
    constant_value: Any | None = None


class ConfigResource(BaseModel):
    model_config = ConfigDict(extra="ignore")

    address: str
    depends_on: list[str] = Field(default_factory=list)
    expressions: dict[str, ExpressionValue] = Field(default_factory=dict)


class ConfigModuleCall(BaseModel):
    model_config = ConfigDict(extra="ignore")

    depends_on: list[str] = Field(default_factory=list)
    expressions: dict[str, ExpressionValue] = Field(default_factory=dict)
    module: ConfigModule | None = None


class ConfigModule(BaseModel):
    model_config = ConfigDict(extra="ignore")

    resources: list[ConfigResource] = Field(default_factory=list)
    module_calls: dict[str, ConfigModuleCall] = Field(default_factory=dict)


class PlanConfiguration(BaseModel):
    model_config = ConfigDict(extra="ignore")

    root_module: ConfigModule | None = None


class PlanWithConfiguration(BaseModel):
    model_config = ConfigDict(extra="ignore")

    configuration: PlanConfiguration | None = None


def build_apply_blockers(plan_path: Path) -> dict[str, frozenset[str]]:
    plan = parser.parse_plan_file(plan_path)
    apply_addrs = frozenset(apply_state.seed_apply_addrs(plan))
    raw: JsonObject = json.loads(plan_path.read_text())
    wrapper = PlanWithConfiguration.model_validate(raw)
    if wrapper.configuration is None or wrapper.configuration.root_module is None or not apply_addrs:
        return {}
    norm_index = _build_norm_index(apply_addrs)
    blockers: dict[str, frozenset[str]] = {}
    _walk_module(
        wrapper.configuration.root_module,
        module_path="",
        var_bindings={},
        apply_addrs=apply_addrs,
        norm_index=norm_index,
        blockers=blockers,
    )
    return blockers


def _build_norm_index(apply_addrs: frozenset[str]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for addr in apply_addrs:
        index.setdefault(_norm_addr(addr), []).append(addr)
    return index


def _norm_addr(addr: str) -> str:
    return _NORM_INDEX.sub("", addr)


def collect_references(value: JsonValue) -> set[str]:
    refs: set[str] = set()
    match value:
        case dict() as obj:
            match obj.get("references"):
                case list() as ref_list:
                    for item in ref_list:
                        match item:
                            case str() as ref:
                                refs.add(ref)
            for nested in obj.values():
                refs |= collect_references(nested)
        case list() as items:
            for item in items:
                refs |= collect_references(item)
    return refs


def _walk_module(
    module: ConfigModule,
    *,
    module_path: str,
    var_bindings: dict[str, frozenset[str]],
    apply_addrs: frozenset[str],
    norm_index: dict[str, list[str]],
    blockers: dict[str, frozenset[str]],
) -> None:
    _register_resource_blockers(
        module,
        module_path=module_path,
        var_bindings=var_bindings,
        apply_addrs=apply_addrs,
        norm_index=norm_index,
        blockers=blockers,
    )
    _walk_module_calls(
        module,
        module_path=module_path,
        apply_addrs=apply_addrs,
        norm_index=norm_index,
        blockers=blockers,
    )


def _register_resource_blockers(
    module: ConfigModule,
    *,
    module_path: str,
    var_bindings: dict[str, frozenset[str]],
    apply_addrs: frozenset[str],
    norm_index: dict[str, list[str]],
    blockers: dict[str, frozenset[str]],
) -> None:
    for resource in module.resources:
        cfg_addr = f"{module_path}{resource.address}"
        candidates = norm_index.get(_norm_addr(cfg_addr), [])
        if not candidates:
            continue
        refs = _resource_refs(resource)
        resolved: set[str] = set()
        for ref in refs:
            resolved |= _resolve_ref(ref, module_path, apply_addrs, norm_index, var_bindings)
        for apply_addr in candidates:
            blockers[apply_addr] = frozenset(resolved - {apply_addr})


def _resource_refs(resource: ConfigResource) -> set[str]:
    refs: set[str] = set(resource.depends_on)
    for expression in resource.expressions.values():
        refs |= collect_references(expression)
    return refs


def _walk_module_calls(
    module: ConfigModule,
    *,
    module_path: str,
    apply_addrs: frozenset[str],
    norm_index: dict[str, list[str]],
    blockers: dict[str, frozenset[str]],
) -> None:
    for call_name, call in module.module_calls.items():
        child_bindings = _var_bindings_from_call(call, module_path, apply_addrs, norm_index)
        if call.module is not None:
            _walk_module(
                call.module,
                module_path=f"{module_path}module.{call_name}.",
                var_bindings=child_bindings,
                apply_addrs=apply_addrs,
                norm_index=norm_index,
                blockers=blockers,
            )


def _var_bindings_from_call(
    call: ConfigModuleCall,
    module_path: str,
    apply_addrs: frozenset[str],
    norm_index: dict[str, list[str]],
) -> dict[str, frozenset[str]]:
    bindings: dict[str, frozenset[str]] = {}
    for input_name, expression in call.expressions.items():
        resolved: set[str] = set()
        for ref in collect_references(expression):
            resolved |= _resolve_ref(ref, module_path, apply_addrs, norm_index, {})
        bindings[input_name] = frozenset(resolved)
    return bindings


def _resolve_ref(
    ref: str,
    module_path: str,
    apply_addrs: frozenset[str],
    norm_index: dict[str, list[str]],
    var_bindings: dict[str, frozenset[str]],
) -> frozenset[str]:
    if ref.startswith(_SKIP_PREFIXES):
        return frozenset()
    if ref.startswith("var."):
        var_name = ref.removeprefix("var.").split("[", maxsplit=1)[0]
        return var_bindings.get(var_name, frozenset())
    stripped = _REF_INDEX.sub("", ref)
    if stripped.startswith("data."):
        qualified = stripped if stripped.startswith("module.") else f"{module_path}{stripped}"
        if not _matches_apply_addrs(qualified, apply_addrs, norm_index):
            return frozenset()
    qualified = stripped if stripped.startswith("module.") else f"{module_path}{stripped}"
    return _matches_apply_addrs(qualified, apply_addrs, norm_index)


def _matches_apply_addrs(
    qualified: str,
    apply_addrs: frozenset[str],
    norm_index: dict[str, list[str]],
) -> frozenset[str]:
    matched: set[str] = set()
    normalized = _norm_addr(qualified)
    for addr in apply_addrs:
        if qualified == addr or qualified.startswith(f"{addr}."):
            matched.add(addr)
    for addr in norm_index.get(normalized, []):
        matched.add(addr)
    for addr in apply_addrs:
        norm_addr = _norm_addr(addr)
        if normalized == norm_addr or normalized.startswith(f"{norm_addr}.") or norm_addr.startswith(f"{normalized}."):
            matched.add(addr)
    return frozenset(matched)
