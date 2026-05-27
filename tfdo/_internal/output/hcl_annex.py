from __future__ import annotations

import json
from typing import Any, NamedTuple

import hcl2

from tfdo._internal.output.models import Change, PlanOutput, ResourceChange
from tfdo._internal.output.schema_lookup import SchemaFieldInfo, schema_field_at_path
from tfdo._internal.schema.models import ResourceSchema

_BLOCK_MARKER = "__is_block__"
type MarkMap = dict[str, object] | list[object] | bool


def find_resource_change(plan: PlanOutput, *, address: str) -> ResourceChange:
    for resource in plan.resource_changes:
        if resource.address == address:
            return resource
    raise ValueError(f"resource change not found: {address!r}")


def annex_attr_slice(change: Change, attr_name: str) -> AnnexSlice:
    after = change.after or {}
    if attr_name not in after:
        raise ValueError(f"attribute {attr_name!r} missing from change.after")
    return AnnexSlice(
        value=after[attr_name],
        before_sensitive=_slice_mark_map(change.before_sensitive, attr_name),
        after_sensitive=_slice_mark_map(change.after_sensitive, attr_name),
        after_unknown=_slice_mark_map(change.after_unknown, attr_name),
    )


class AnnexSlice(NamedTuple):
    value: object
    before_sensitive: MarkMap
    after_sensitive: MarkMap
    after_unknown: MarkMap


def render_hcl_annex_as_tf(
    resource: ResourceChange,
    attr_name: str,
    *,
    schema: ResourceSchema | None = None,
) -> str | None:
    change = resource.change
    after = change.after or {}
    if attr_name not in after:
        raise ValueError(f"attribute {attr_name!r} missing from change.after")
    hcl_body = render_hcl_annex(
        after[attr_name],
        attr_name=attr_name,
        before_sensitive=_slice_mark_map(change.before_sensitive, attr_name),
        after_sensitive=_slice_mark_map(change.after_sensitive, attr_name),
        after_unknown=_slice_mark_map(change.after_unknown, attr_name),
        schema=schema,
    )
    if hcl_body is None:
        return None
    indented = _indent_block(hcl_body, spaces=2)
    return "\n".join(
        [
            f"# {resource.address}",
            f"# Annex: {attr_name} after (sensitive and unknown paths stripped)",
            "",
            f'resource "{resource.type}" "{resource.name}" {{',
            indented,
            "}",
            "",
        ]
    )


def _indent_block(text: str, *, spaces: int) -> str:
    pad = " " * spaces
    return "\n".join(f"{pad}{line}" if line else "" for line in text.splitlines())


def render_hcl_annex(
    value: object,
    *,
    attr_name: str,
    before_sensitive: MarkMap,
    after_sensitive: MarkMap,
    after_unknown: MarkMap,
    schema: ResourceSchema | None = None,
) -> str | None:
    stripped = strip_annex_value(
        value,
        before_sensitive=before_sensitive,
        after_sensitive=after_sensitive,
        after_unknown=after_unknown,
    )
    if stripped is None:
        return None
    try:
        hcl_dict = _value_to_hcl_root(stripped, attr_name=attr_name, schema=schema)
        return _compact_hcl(hcl2.dumps(hcl_dict).rstrip())
    except (TypeError, ValueError):
        return None


def render_json_annex(
    value: object,
    *,
    before_sensitive: MarkMap,
    after_sensitive: MarkMap,
    after_unknown: MarkMap,
) -> str:
    stripped = strip_annex_value(
        value,
        before_sensitive=before_sensitive,
        after_sensitive=after_sensitive,
        after_unknown=after_unknown,
    )
    if stripped is None:
        return "null"
    return json.dumps(stripped, sort_keys=True, indent=2)


def strip_annex_value(
    value: object,
    *,
    before_sensitive: MarkMap,
    after_sensitive: MarkMap,
    after_unknown: MarkMap,
) -> object | None:
    return strip_marked_paths(
        value,
        before_sensitive,
        after_sensitive,
        after_unknown,
    )


def strip_marked_paths(value: object, *mark_maps: MarkMap) -> object | None:
    if any(mark is True for mark in mark_maps):
        return None
    active: list[MarkMap] = [mark for mark in mark_maps if mark not in (False, True)]
    if not active:
        return value

    match value:
        case dict():
            return _strip_dict(value, active)
        case list():
            return _strip_list(value, active)
        case _:
            return value


def _strip_dict(value: dict[str, object], mark_maps: list[MarkMap]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, child in value.items():
        child_maps = [_child_mark(mark, key) for mark in mark_maps]
        if _subtree_marked(child_maps):
            continue
        stripped = strip_marked_paths(child, *child_maps)
        if stripped is None or stripped == {} or stripped == []:
            continue
        result[key] = stripped
    return result


def _strip_list(value: list[object], mark_maps: list[MarkMap]) -> list[object]:
    result_list: list[object] = []
    for index, child in enumerate(value):
        child_maps = [_child_mark_index(mark, index) for mark in mark_maps]
        if _subtree_marked(child_maps):
            continue
        stripped = strip_marked_paths(child, *child_maps)
        if stripped is None or stripped == {} or stripped == []:
            continue
        result_list.append(stripped)
    return result_list


def _slice_mark_map(mark_map: MarkMap, attr_name: str) -> MarkMap:
    if isinstance(mark_map, bool):
        return mark_map
    if isinstance(mark_map, list):
        return False
    child = mark_map.get(attr_name, False)
    return child if isinstance(child, dict | list | bool) else False


def _child_mark(mark_map: MarkMap, key: str) -> MarkMap:
    if isinstance(mark_map, bool):
        return mark_map
    if isinstance(mark_map, list):
        return False
    if key not in mark_map:
        return False
    child = mark_map[key]
    if child is True:
        return True
    if child == {}:
        return False
    return child if isinstance(child, dict | list) else False


def _child_mark_index(mark_map: MarkMap, index: int) -> MarkMap:
    if isinstance(mark_map, bool):
        return mark_map
    if isinstance(mark_map, list):
        if index >= len(mark_map):
            return False
        child = mark_map[index]
        if child is True:
            return True
        if child == {}:
            return False
        return child if isinstance(child, dict | list) else False
    return False


def _subtree_marked(maps: list[MarkMap]) -> bool:
    return any(mark is True for mark in maps)


def _value_to_hcl_root(value: object, *, attr_name: str, schema: ResourceSchema | None) -> dict[str, Any]:
    return {attr_name: _convert_at_path(value, (attr_name,), schema)}


def _convert_at_path(value: object, path: tuple[str | int, ...], schema: ResourceSchema | None) -> Any:
    field = _field_info(path, schema)
    match value:
        case None:
            raise ValueError("null values should be omitted before HCL conversion")
        case str():
            return f'"{value}"'
        case bool() | int() | float():
            return value
        case dict():
            fields = _convert_object_fields(value, path, schema)
            if field is not None and field.is_block:
                return [{_BLOCK_MARKER: True, **fields}]
            return fields
        case list():
            return _convert_list(value, path, schema, field)
        case _:
            raise TypeError(f"unsupported plan value type: {type(value)!r}")


def _convert_list(
    value: list[object],
    path: tuple[str | int, ...],
    schema: ResourceSchema | None,
    field: SchemaFieldInfo | None,
) -> list[Any]:
    if field is not None and field.is_block:
        return [
            {_BLOCK_MARKER: True, **_convert_object_fields(item, path, schema)}
            for item in value
            if isinstance(item, dict)
        ]
    return [
        _convert_object_fields(item, path, schema) if isinstance(item, dict) else _convert_at_path(item, path, schema)
        for item in value
    ]


def _convert_object_fields(
    value: dict[str, object],
    path: tuple[str | int, ...],
    schema: ResourceSchema | None,
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key, child in value.items():
        if child is None:
            continue
        fields[key] = _convert_at_path(child, (*path, key), schema)
    return fields


def _field_info(path: tuple[str | int, ...], schema: ResourceSchema | None) -> SchemaFieldInfo | None:
    if schema is None:
        return None
    return schema_field_at_path(schema, path)


def _compact_hcl(text: str) -> str:
    lines: list[str] = []
    prev_blank = False
    for line in text.splitlines():
        blank = not line.strip()
        if blank and prev_blank:
            continue
        lines.append(line.rstrip())
        prev_blank = blank
    return "\n".join(lines).rstrip()
