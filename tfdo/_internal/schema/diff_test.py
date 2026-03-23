from __future__ import annotations

import pytest

from tfdo._internal.schema.diff import (
    compute_schema_diff,
    resolve_schema_diff_sides,
)
from tfdo._internal.schema.models import ResourceSchema, SchemaAttribute, SchemaBlock, SchemaBlockType


def test_resolve_schema_diff_sides_inference_and_errors() -> None:
    a, b = resolve_schema_diff_sides("1.0.0", None)
    assert a.version_constraint == "1.0.0" and not a.use_dev_overrides
    assert b.use_dev_overrides
    x, y = resolve_schema_diff_sides(None, ">= 2")
    assert x.use_dev_overrides and not y.use_dev_overrides
    with pytest.raises(ValueError, match="dev to dev"):
        resolve_schema_diff_sides("dev", "dev")


def test_compute_schema_diff_type_required_and_path_filter() -> None:
    left = ResourceSchema(
        block=SchemaBlock(
            attributes={
                "keep": SchemaAttribute(type="string", required=True),
                "drop": SchemaAttribute(type="string"),
            },
        ),
    )
    right = ResourceSchema(
        block=SchemaBlock(
            attributes={
                "keep": SchemaAttribute(type="number", required=False),
                "drop": SchemaAttribute(type="string"),
            },
        ),
    )
    added, removed, changes = compute_schema_diff(
        left_map={"r": left},
        right_map={"r": right},
        attribute_paths=["keep"],
        resource_filter=None,
    )
    assert not added and not removed
    assert len(changes) == 1
    assert changes[0].path == "keep" and changes[0].kind == "changed"
    assert "type" in changes[0].tags and "required_to_optional" in changes[0].tags


def test_compute_schema_diff_nested_block_path() -> None:
    left = ResourceSchema(
        block=SchemaBlock(
            block_types={
                "timeouts": SchemaBlockType(
                    block=SchemaBlock(attributes={"delete": SchemaAttribute(type="string")}),
                    nesting_mode="single",
                ),
            },
        ),
    )
    right = ResourceSchema(
        block=SchemaBlock(
            block_types={
                "timeouts": SchemaBlockType(
                    block=SchemaBlock(attributes={"delete": SchemaAttribute(type="number")}),
                    nesting_mode="single",
                ),
            },
        ),
    )
    _, _, changes = compute_schema_diff(
        left_map={"r": left},
        right_map={"r": right},
        attribute_paths=None,
        resource_filter=None,
    )
    assert any(c.path == "timeouts.delete" and c.kind == "changed" for c in changes)
