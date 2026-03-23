from __future__ import annotations

from tfdo._internal.schema.models import ResourceSchema, SchemaAttribute, SchemaBlock


def is_computed_only_attribute(attr: SchemaAttribute) -> bool:
    if attr.computed is not True:
        return False
    if attr.optional is True:
        return False
    return True


def is_whole_map_leaf_attribute(attr: SchemaAttribute) -> bool:
    if attr.nested_type is not None:
        return False
    t = attr.type
    return isinstance(t, list) and bool(t) and t[0] == "map"


def _emit_nested_type_children(parent: str, nested: SchemaBlock, out: set[str]) -> None:
    for child_name, child_attr in (nested.attributes or {}).items():
        if is_computed_only_attribute(child_attr):
            continue
        out.add(f"{parent}.{child_name}")


def resource_schema_input_paths(schema: ResourceSchema) -> frozenset[str]:
    out: set[str] = set()
    block = schema.block
    for name, attr in (block.attributes or {}).items():
        if is_computed_only_attribute(attr):
            continue
        if attr.nested_type is not None and (attr.nested_type.attributes or {}):
            _emit_nested_type_children(name, attr.nested_type, out)
            continue
        out.add(name)
    for bt_name, bt in (block.block_types or {}).items():
        inner = bt.block.attributes or {}
        for inner_name, inner_attr in inner.items():
            if is_computed_only_attribute(inner_attr):
                continue
            out.add(f"{bt_name}.{inner_name}")
    return frozenset(out)
