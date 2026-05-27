from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from tfdo._internal.output.create_filter import is_empty_create_value
from tfdo._internal.output.display_path import resolve_replace_display_keys, values_for_display_key
from tfdo._internal.output.models import Change, ResourceAction


class AttrPrefix(StrEnum):
    ADD = "+"
    CHANGE = "~"
    REPLACE = "!"
    REMOVE = "-"


class ValueKind(StrEnum):
    SCALAR = "scalar"
    COMPLEX = "complex"


class AttrLine(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    prefix: AttrPrefix | None = None
    old_value: object | None = None
    new_value: object | None = None
    is_sensitive: bool = False
    value_kind: ValueKind = ValueKind.SCALAR


def compute_attr_lines(
    change: Change,
    required_attrs: frozenset[str],
    *,
    show_create_defaults: bool = False,
) -> list[AttrLine]:
    action = change.action()
    before = change.before or {}
    after = change.after or {}
    match action:
        case ResourceAction.CREATE:
            lines = _create_lines(before, after, change, required_attrs, show_create_defaults)
        case ResourceAction.UPDATE:
            lines = _update_lines(before, after, change, required_attrs)
        case ResourceAction.DELETE:
            lines = _delete_lines(before, change, required_attrs)
        case ResourceAction.REPLACE_DESTROY_FIRST | ResourceAction.REPLACE_CREATE_FIRST:
            lines = _replace_lines(before, after, change, required_attrs)
        case _:
            lines = []
    return _sort_attr_lines(lines)


def _create_lines(
    before: dict[str, object],
    after: dict[str, object],
    change: Change,
    required_attrs: frozenset[str],
    show_create_defaults: bool,
) -> list[AttrLine]:
    lines: list[AttrLine] = []
    for name in sorted(required_attrs):
        if _is_after_unknown(change.after_unknown, name):
            continue
        if name not in after:
            continue
        lines.append(_line(name, None, None, after[name], change))
    for name in sorted(after):
        if name in required_attrs or _is_after_unknown(change.after_unknown, name):
            continue
        value = after[name]
        if not show_create_defaults and _skip_create_attr(value):
            continue
        lines.append(_line(name, AttrPrefix.ADD, None, value, change))
    return lines


def _skip_create_attr(value: object) -> bool:
    return is_empty_create_value(value)


def _update_lines(
    before: dict[str, object],
    after: dict[str, object],
    change: Change,
    required_attrs: frozenset[str],
) -> list[AttrLine]:
    lines: list[AttrLine] = []
    changed = _top_level_changed_keys(before, after)
    removed = _removed_keys(before, after)
    for name in sorted(required_attrs):
        if name not in before or _is_after_unknown(change.after_unknown, name):
            continue
        before_val = before[name]
        if name in after:
            after_val = after[name]
            if before_val != after_val:
                continue
        else:
            after_val = before_val
        lines.append(_line(name, None, before_val, after_val, change))
    for name in sorted(changed - removed):
        if _is_after_unknown(change.after_unknown, name):
            continue
        lines.append(_line(name, AttrPrefix.CHANGE, before.get(name), after.get(name), change))
    for name in sorted(removed):
        if name in required_attrs:
            continue
        lines.append(_line(name, AttrPrefix.REMOVE, before.get(name), None, change))
    return lines


def _delete_lines(
    before: dict[str, object],
    change: Change,
    required_attrs: frozenset[str],
) -> list[AttrLine]:
    lines: list[AttrLine] = []
    for name in sorted(required_attrs):
        if name not in before:
            continue
        lines.append(_line(name, None, before[name], None, change))
    return lines


def _replace_lines(
    before: dict[str, object],
    after: dict[str, object],
    change: Change,
    required_attrs: frozenset[str],
) -> list[AttrLine]:
    lines: list[AttrLine] = []
    replace_keys = resolve_replace_display_keys(change.replace_paths, before, after)
    changed = _top_level_changed_keys(before, after)
    replace_roots = {key.split("[", 1)[0].split(".", 1)[0] for key in replace_keys}

    for name in sorted(required_attrs):
        if name not in before or name not in after:
            continue
        if before.get(name) != after.get(name):
            continue
        if _is_after_unknown(change.after_unknown, name):
            continue
        lines.append(_line(name, None, before[name], after[name], change))

    for key in sorted(replace_keys):
        old, new = values_for_display_key(key, before, after)
        lines.append(_line(key, AttrPrefix.REPLACE, old, new, change))

    for name in sorted(changed - replace_roots):
        if _is_after_unknown(change.after_unknown, name):
            continue
        lines.append(_line(name, AttrPrefix.CHANGE, before.get(name), after.get(name), change))

    return lines


def _line(
    name: str,
    prefix: AttrPrefix | None,
    old: object | None,
    new: object | None,
    change: Change,
) -> AttrLine:
    top_level = name.split("[", 1)[0].split(".", 1)[0]
    sensitive = _is_sensitive(change.before_sensitive, change.after_sensitive, top_level)
    if sensitive:
        old, new = None, None
    kind = ValueKind.COMPLEX if _is_complex(old) or _is_complex(new) else ValueKind.SCALAR
    return AttrLine(name=name, prefix=prefix, old_value=old, new_value=new, is_sensitive=sensitive, value_kind=kind)


def _is_after_unknown(after_unknown: dict[str, object] | bool, key: str) -> bool:
    return isinstance(after_unknown, dict) and after_unknown.get(key) is True


def _is_sensitive(
    before_sensitive: dict[str, object] | bool,
    after_sensitive: dict[str, object] | bool,
    key: str,
) -> bool:
    if before_sensitive is True or after_sensitive is True:
        return True
    if isinstance(before_sensitive, dict) and before_sensitive.get(key) is True:
        return True
    return isinstance(after_sensitive, dict) and after_sensitive.get(key) is True


def _is_complex(value: object | None) -> bool:
    return isinstance(value, dict | list)


def _top_level_changed_keys(before: dict[str, object], after: dict[str, object]) -> set[str]:
    keys = set(before) | set(after)
    return {key for key in keys if before.get(key) != after.get(key)}


def _removed_keys(before: dict[str, object], after: dict[str, object]) -> set[str]:
    return {key for key in before if key not in after}


def _sort_attr_lines(lines: list[AttrLine]) -> list[AttrLine]:
    unchanged = sorted((line for line in lines if line.prefix is None), key=lambda line: line.name)
    changed = [line for line in lines if line.prefix is not None]
    replace = sorted((line for line in changed if line.prefix == AttrPrefix.REPLACE), key=lambda line: line.name)
    rest = sorted((line for line in changed if line.prefix != AttrPrefix.REPLACE), key=lambda line: line.name)
    return [*unchanged, *replace, *rest]
