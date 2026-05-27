from __future__ import annotations

from collections.abc import Callable

from tfdo._internal.output import display_path
from tfdo._internal.output.attr_diff import AttrLine, AttrPrefix, ValueKind
from tfdo._internal.output.display_path import parse_display_key, path_get_value
from tfdo._internal.output.models import Change, ResourceAction
from tfdo._internal.output.tree_builder import ResourceNode

ComputedOnlyLookup = Callable[[str, str, tuple[str | int, ...]], bool | None]

_CREATE_ACTIONS = frozenset({ResourceAction.CREATE})
_DRIFT_ALLOWLIST = frozenset({"updated", "labels", "effective_labels", "terraform_labels"})
KNOWN_AFTER_APPLY = "(known after apply)"


def after_unknown_at(change: Change, path: tuple[str | int, ...]) -> bool:
    return after_unknown_at_map(change.after_unknown, path)


def after_unknown_at_map(unknown: object | bool | None, path: tuple[str | int, ...]) -> bool:
    if unknown is True:
        return True
    if not isinstance(unknown, dict):
        return False
    current: object = unknown
    for part in path:
        match current, part:
            case dict(), str() as key:
                next_val = current.get(key)
            case list(), int() as index:
                if index < 0 or index >= len(current):
                    return False
                next_val = current[index]
            case _:
                return False
        if next_val is True:
            return True
        current = next_val
    return False


def is_computed_only_plan_delta(
    path: tuple[str | int, ...],
    change: Change,
    lookup: ComputedOnlyLookup,
    *,
    provider: str,
    resource_type: str,
) -> bool:
    if change.action() in _CREATE_ACTIONS:
        return after_unknown_at(change, path)
    before_val, after_val = (
        path_get_value(change.before, list(path)),
        path_get_value(change.after, list(path)),
    )
    if before_val is not None and after_val is not None and before_val != after_val:
        return False
    if after_unknown_at(change, path):
        return True
    schema_hit = lookup(provider, resource_type, path)
    if schema_hit is True:
        return True
    if schema_hit is False:
        return False
    if len(path) == 1 and isinstance(path[0], str):
        root = path[0]
        before = change.before or {}
        after = change.after or {}
        if root in before and root not in after:
            return True
    return False


def is_computed_only_drift_line(
    line: AttrLine,
    change: Change,
    lookup: ComputedOnlyLookup,
    *,
    provider: str,
    resource_type: str,
) -> bool:
    if line.prefix is None:
        return True
    path = tuple(parse_display_key(line.name))
    if path and path[0] in _DRIFT_ALLOWLIST:
        return True
    if path and isinstance(path[0], str):
        root_hit = lookup(provider, resource_type, (path[0],))
        if root_hit is True:
            return True
    if after_unknown_at(change, path):
        return True
    schema_hit = lookup(provider, resource_type, path)
    if schema_hit is True:
        return True
    return False


def is_computed_only_drift_resource(
    node: ResourceNode,
    attr_lines: list[AttrLine],
    lookup: ComputedOnlyLookup,
    *,
    provider: str,
) -> bool:
    if node.action == ResourceAction.DELETE:
        return False
    changed = [line for line in attr_lines if line.prefix is not None]
    if not changed:
        return True
    return all(
        is_computed_only_drift_line(
            line,
            node.change,
            lookup,
            provider=provider,
            resource_type=node.type,
        )
        for line in changed
    )


def truncate_inline_rendered(rendered: str, *, budget: int) -> str:
    if len(rendered) <= budget:
        return rendered
    return rendered[: max(1, budget - 1)] + "…"


def format_computed_before_value(value: object, *, budget: int) -> str:
    return truncate_inline_rendered(display_path.inline_json(value), budget=budget)


def format_computed_delta_line(
    line: AttrLine,
    *,
    change: Change,
    path: tuple[str | int, ...],
    budget: int,
) -> AttrLine:
    unknown = after_unknown_at(change, path)
    prefix = AttrPrefix.CHANGE if unknown else line.prefix
    old_value = line.old_value
    value_kind = line.value_kind
    if old_value is not None and value_kind == ValueKind.COMPLEX:
        old_value = format_computed_before_value(old_value, budget=budget)
        value_kind = ValueKind.SCALAR
    new_value = KNOWN_AFTER_APPLY if unknown else line.new_value
    return AttrLine(
        name=line.name,
        prefix=prefix,
        old_value=old_value,
        new_value=new_value,
        is_sensitive=line.is_sensitive,
        value_kind=value_kind,
    )


def format_computed_structural_line(
    line: str,
    stripped: str,
    *,
    change: Change,
    path: tuple[str | int, ...],
    budget: int,
) -> str:
    indent = line[: len(line) - len(stripped)]
    key, _, value_part = stripped.partition(": ")
    marker, _, path_s = key.partition(" ")
    if after_unknown_at(change, path):
        marker = AttrPrefix.CHANGE
        old_s = value_part.split(" -> ", 1)[0] if " -> " in value_part else value_part
        value_part = f"{truncate_inline_rendered(old_s, budget=budget)} -> {KNOWN_AFTER_APPLY}"
    return f"{indent}{marker} {path_s}: {value_part}"


def filter_attr_lines(
    lines: list[AttrLine],
    *,
    change: Change,
    lookup: ComputedOnlyLookup,
    provider: str,
    resource_type: str,
    show_computed_deltas: bool,
    budget: int,
) -> list[AttrLine]:
    kept: list[AttrLine] = []
    for line in lines:
        if line.prefix is None:
            kept.append(line)
            continue
        path = tuple(parse_display_key(line.name))
        if is_computed_only_plan_delta(
            path,
            change,
            lookup,
            provider=provider,
            resource_type=resource_type,
        ):
            if show_computed_deltas:
                kept.append(
                    format_computed_delta_line(
                        line,
                        change=change,
                        path=path,
                        budget=budget,
                    )
                )
            continue
        kept.append(line)
    return kept
