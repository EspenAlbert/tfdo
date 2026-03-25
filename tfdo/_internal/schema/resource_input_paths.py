from __future__ import annotations

from tfdo._internal.schema.models import ResourceSchema, SchemaAttribute, SchemaBlock

_DEFAULT_MAX_DEPTH = 1


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


def _walk_block(
    block: SchemaBlock,
    prefix: str,
    depth: int,
    max_depth: int,
    include_computed: bool,
    out: set[str],
    seen: set[int],
) -> None:
    block_id = id(block)
    if block_id in seen:
        return
    seen.add(block_id)

    for name, attr in (block.attributes or {}).items():
        if not include_computed and is_computed_only_attribute(attr):
            continue
        full = f"{prefix}.{name}" if prefix else name
        if attr.nested_type is not None and (attr.nested_type.attributes or {}) and depth < max_depth:
            _walk_block(attr.nested_type, full, depth + 1, max_depth, include_computed, out, seen)
            continue
        out.add(full)

    for bt_name, bt in (block.block_types or {}).items():
        full = f"{prefix}.{bt_name}" if prefix else bt_name
        if depth < max_depth:
            _walk_block(bt.block, full, depth + 1, max_depth, include_computed, out, seen)
        else:
            out.add(full)

    seen.discard(block_id)


def resource_schema_input_paths(
    schema: ResourceSchema,
    *,
    max_depth: int = _DEFAULT_MAX_DEPTH,
    include_computed: bool = False,
) -> frozenset[str]:
    out: set[str] = set()
    _walk_block(schema.block, "", 0, max_depth, include_computed, out, set())
    return frozenset(out)
