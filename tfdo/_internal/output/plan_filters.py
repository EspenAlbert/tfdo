from __future__ import annotations

from collections.abc import Callable

from tfdo._internal.output.attr_diff import AttrLine
from tfdo._internal.output.display_path import parse_display_key, path_get_value
from tfdo._internal.output.models import Change, ResourceAction
from tfdo._internal.output.tree_builder import ResourceNode

ComputedOnlyLookup = Callable[[str, str, tuple[str | int, ...]], bool | None]

_DRIFT_ALLOWLIST = frozenset({"updated", "labels", "effective_labels", "terraform_labels"})


def after_unknown_at(change: Change, path: tuple[str | int, ...]) -> bool:
    unknown = change.after_unknown
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


def filter_attr_lines(
    lines: list[AttrLine],
    *,
    change: Change,
    lookup: ComputedOnlyLookup,
    provider: str,
    resource_type: str,
    show_computed_deltas: bool,
) -> list[AttrLine]:
    if show_computed_deltas:
        return lines
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
            continue
        kept.append(line)
    return kept
