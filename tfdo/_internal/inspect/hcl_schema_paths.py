from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from tfdo._internal.inspect import hcl_resource_paths
from tfdo._internal.schema import resource_input_paths as rip
from tfdo._internal.schema.models import ResourceSchema, SchemaAttribute, SchemaBlock, SchemaBlockType


class AssistedResourcePathsResult(BaseModel):
    attribute_paths: frozenset[str] = Field(default_factory=frozenset)
    unknown_in_config: frozenset[str] = Field(default_factory=frozenset)
    invalid_in_config: frozenset[str] = Field(default_factory=frozenset)


def _lookup(schema: ResourceSchema, key: str) -> tuple[SchemaAttribute | None, SchemaBlockType | None]:
    block = schema.block
    attrs = block.attributes or {}
    bts = block.block_types or {}
    if key in attrs:
        return attrs[key], None
    if key in bts:
        return None, bts[key]
    return None, None


def collect_resource_body_paths_assisted(body: dict[str, Any], schema: ResourceSchema) -> AssistedResourcePathsResult:
    attr_paths: set[str] = set()
    unknown: set[str] = set()
    invalid: set[str] = set()
    for key, value in body.items():
        if hcl_resource_paths._is_terraform_meta_path(key):
            continue
        if key == "dynamic":
            _collect_dynamic_assisted(value, schema, attr_paths, unknown, invalid)
            continue
        attr, bt = _lookup(schema, key)
        if attr is None and bt is None:
            unknown.add(key)
            continue
        if bt is not None:
            _collect_block_type_key(key, bt, value, attr_paths, unknown, invalid)
            continue
        assert attr is not None
        _collect_attribute_key(key, attr, value, attr_paths, unknown, invalid)
    return AssistedResourcePathsResult(
        attribute_paths=frozenset(attr_paths),
        unknown_in_config=frozenset(unknown),
        invalid_in_config=frozenset(invalid),
    )


def _collect_block_type_key(
    name: str,
    bt: SchemaBlockType,
    value: Any,
    attr_paths: set[str],
    unknown: set[str],
    invalid: set[str],
) -> None:
    if not hcl_resource_paths._is_nested_block_list(value):
        invalid.add(name)
        return
    inner_attrs = bt.block.attributes or {}
    for block in value:
        if not isinstance(block, dict):
            continue
        for arg, val in block.items():
            if hcl_resource_paths._is_nested_block_list(val):
                continue
            if arg not in inner_attrs:
                unknown.add(f"{name}.{arg}")
                continue
            child = inner_attrs[arg]
            if rip.is_computed_only_attribute(child):
                invalid.add(f"{name}.{arg}")
                continue
            if isinstance(val, dict) and val:
                invalid.add(f"{name}.{arg}")
                continue
            attr_paths.add(f"{name}.{arg}")


def _list_element_child_path(
    name: str,
    ck: str,
    cv: Any,
    ca: SchemaAttribute,
    attr_paths: set[str],
    unknown: set[str],
    invalid: set[str],
) -> None:
    if rip.is_computed_only_attribute(ca):
        invalid.add(f"{name}.{ck}")
        return
    if hcl_resource_paths._is_nested_block_list(cv):
        attr_paths.add(f"{name}.{ck}")
        return
    if rip.is_whole_map_leaf_attribute(ca):
        if isinstance(cv, dict) and cv:
            attr_paths.add(f"{name}.{ck}")
        elif cv not in (None, {}, []):
            invalid.add(f"{name}.{ck}")
        return
    if ca.nested_type is not None and (ca.nested_type.attributes or {}):
        if isinstance(cv, dict) and cv:
            invalid.add(f"{name}.{ck}")
        elif cv not in (None, {}, []):
            invalid.add(f"{name}.{ck}")
        return
    attr_paths.add(f"{name}.{ck}")


def _collect_attr_list_element_paths(
    name: str,
    elem_attrs: dict[str, SchemaAttribute],
    value: list[Any],
    attr_paths: set[str],
    unknown: set[str],
    invalid: set[str],
) -> None:
    for item in value:
        if not isinstance(item, dict):
            continue
        for ck, cv in item.items():
            if ck not in elem_attrs:
                unknown.add(f"{name}.{ck}")
                continue
            _list_element_child_path(name, ck, cv, elem_attrs[ck], attr_paths, unknown, invalid)


def _collect_attr_nested_single_paths(
    name: str,
    nt: SchemaBlock,
    value: dict[str, Any],
    attr_paths: set[str],
    unknown: set[str],
    invalid: set[str],
) -> None:
    attrs = nt.attributes or {}
    for sk, sv in value.items():
        if sk not in attrs:
            unknown.add(f"{name}.{sk}")
            continue
        sa = attrs[sk]
        if rip.is_computed_only_attribute(sa):
            invalid.add(f"{name}.{sk}")
            continue
        if hcl_resource_paths._is_nested_block_list(sv):
            invalid.add(f"{name}.{sk}")
            continue
        if isinstance(sv, dict) and sv:
            invalid.add(f"{name}.{sk}")
            continue
        attr_paths.add(f"{name}.{sk}")


def _collect_attribute_nonlist(
    name: str,
    attr: SchemaAttribute,
    value: Any,
    attr_paths: set[str],
    unknown: set[str],
    invalid: set[str],
) -> None:
    if isinstance(value, dict):
        if not value:
            return
        if rip.is_whole_map_leaf_attribute(attr):
            attr_paths.add(name)
            return
        nt = attr.nested_type
        if nt is not None and (nt.attributes or {}):
            _collect_attr_nested_single_paths(name, nt, value, attr_paths, unknown, invalid)
            return
        invalid.add(name)
        return
    if rip.is_whole_map_leaf_attribute(attr):
        invalid.add(name)
        return
    if isinstance(value, list):
        if value:
            attr_paths.add(name)
        return
    attr_paths.add(name)


def _collect_attribute_key(
    name: str,
    attr: SchemaAttribute,
    value: Any,
    attr_paths: set[str],
    unknown: set[str],
    invalid: set[str],
) -> None:
    if value is None:
        return
    if rip.is_computed_only_attribute(attr):
        invalid.add(name)
        return
    if hcl_resource_paths._is_nested_block_list(value):
        nt = attr.nested_type
        if nt is None or nt.nesting_mode not in ("list", "set"):
            invalid.add(name)
            return
        _collect_attr_list_element_paths(name, nt.attributes or {}, value, attr_paths, unknown, invalid)
        return
    _collect_attribute_nonlist(name, attr, value, attr_paths, unknown, invalid)


def _schema_block_for_dynamic_label(schema: ResourceSchema, label: str) -> SchemaBlock | None:
    bts = schema.block.block_types or {}
    if label in bts:
        return bts[label].block
    attrs = schema.block.attributes or {}
    if label in attrs:
        a = attrs[label]
        if a.nested_type is not None:
            return a.nested_type
    return None


def _collect_dynamic_item(
    label: str,
    dyn_body: Any,
    schema: ResourceSchema,
    attr_paths: set[str],
    unknown: set[str],
    invalid: set[str],
) -> None:
    ctx = _schema_block_for_dynamic_label(schema, label)
    if not isinstance(dyn_body, dict):
        return
    contents = dyn_body.get("content")
    if not isinstance(contents, list):
        return
    attrs = ctx.attributes if ctx is not None else None
    for content_block in contents:
        if not isinstance(content_block, dict):
            continue
        for arg, val in content_block.items():
            prefix = f"{label}.{arg}"
            if not attrs or arg not in attrs:
                unknown.add(prefix)
                continue
            _collect_attribute_key(prefix, attrs[arg], val, attr_paths, unknown, invalid)


def _collect_dynamic_assisted(
    value: Any,
    schema: ResourceSchema,
    attr_paths: set[str],
    unknown: set[str],
    invalid: set[str],
) -> None:
    if not isinstance(value, list):
        return
    for item in value:
        if not isinstance(item, dict):
            continue
        for label, dyn_body in item.items():
            _collect_dynamic_item(label, dyn_body, schema, attr_paths, unknown, invalid)
