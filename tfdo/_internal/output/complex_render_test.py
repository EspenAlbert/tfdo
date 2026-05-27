from __future__ import annotations

import json

from tfdo._internal.output.complex_render import (
    SEE_ABOVE_FOR_FULL_CONFIG,
    ComplexRenderConfig,
    render_complex_value,
)
from tfdo._internal.output.models import Change
from tfdo._internal.output.schema_lookup import CollectionKind, build_schema_lookups_from_index
from tfdo._internal.output.testdata_paths import TESTDATA_DIR
from tfdo._internal.schema.models import ResourceSchema

_ADDR = "aws_security_group.allow_tls"
_WIDE = 200
_INDENT = 6


def _render(
    old: object | None,
    new: object | None,
    *,
    attr_name: str = "tags",
    collection_kind: CollectionKind | None = None,
    terminal_width: int = _WIDE,
    indent: int = _INDENT,
    config: ComplexRenderConfig | None = None,
    is_sensitive: bool = False,
    show_full_config_annex: bool = False,
) -> tuple[list[str], str | None]:
    result = render_complex_value(
        old,
        new,
        attr_name=attr_name,
        resource_address=_ADDR,
        indent=indent,
        terminal_width=terminal_width,
        config=config or ComplexRenderConfig(),
        collection_kind=collection_kind,
        is_sensitive=is_sensitive,
        show_full_config_annex=show_full_config_annex,
    )
    header = result.detail_block.header if result.detail_block else None
    return result.inline_lines, header


def _rule(port: int) -> dict[str, object]:
    return {
        "cidr_blocks": ["10.0.0.0/8"],
        "from_port": port,
        "protocol": "tcp",
        "to_port": port,
    }


def _ingress_rules(n: int) -> list[dict[str, object]]:
    return [_rule(80 + i) for i in range(n)]


def test_inline_scalar_list() -> None:
    lines, header = _render(["a", "b"], ["a", "b", "c"])
    assert header is None
    joined = "\n".join(lines)
    assert '["a","b"]' in joined
    assert "-> " in joined
    assert '["a","b","c"]' in joined


def test_inline_dict_sorted_keys() -> None:
    lines, header = _render({"z": 1, "a": 2}, {"a": 2, "z": 3})
    assert header is None
    joined = "\n".join(lines)
    assert '{"a":2,"z":1}' in joined
    assert "-> " in joined
    assert '{"a":2,"z":3}' in joined


def test_per_item_set_insert() -> None:
    before = _ingress_rules(5)
    after = [*before, _rule(8080)]
    lines, header = _render(before, after, attr_name="ingress", collection_kind="set")
    assert header is None
    text = "\n".join(lines)
    assert text.count("+ ") == 1
    assert text.count("- ") == 0
    assert text.count("~ ") == 0


def test_per_item_list_middle_insert() -> None:
    before = _ingress_rules(5)
    after = [before[0], _rule(3000), *before[1:]]
    lines, header = _render(before, after, attr_name="ingress", collection_kind="list")
    assert header is None
    text = "\n".join(lines)
    assert "ingress[1]" in text
    assert "-> " in text
    assert "+ ingress[5]" in text


def test_detail_block_large_dict() -> None:
    old = "x" * 500
    new = "y" * 500
    lines, header = _render(old, new, attr_name="user_data", show_full_config_annex=True)
    assert header == f"--- user_data ({_ADDR}) ---"
    assert any(SEE_ABOVE_FOR_FULL_CONFIG in line for line in lines)


def test_detail_block_suppressed_by_default() -> None:
    old = {"layer": {f"k{i}": "x" * 40 for i in range(8)}}
    new = {"layer": {f"k{i}": "y" * 40 for i in range(8)}}
    lines, header = _render(old, new, attr_name="user_data")
    assert header is None
    assert any("layer" in line for line in lines)


def test_narrow_terminal_uses_inline_min_width() -> None:
    config = ComplexRenderConfig(inline_min_width=120)
    old = "x" * 200
    new = "y" * 200
    lines, header = _render(
        old,
        new,
        terminal_width=40,
        config=config,
        show_full_config_annex=True,
    )
    assert header is not None


def test_sensitive_masks_values() -> None:
    lines, header = _render({"secret": "x"}, {"secret": "y"}, is_sensitive=True)
    assert header is None
    assert lines == ["      (sensitive)"]
    assert "secret" not in "\n".join(lines)


def test_extra_indent_forces_detail_block() -> None:
    lines, header = _render(
        None,
        "z" * 300,
        attr_name="user_data",
        terminal_width=120,
        indent=100,
        config=ComplexRenderConfig(inline_min_width=120),
        show_full_config_annex=True,
    )
    assert header is not None
    assert any(SEE_ABOVE_FOR_FULL_CONFIG in line for line in lines)


def test_per_item_when_list_fits_count_but_not_width() -> None:
    big = {**_rule(80), "notes": "n" * 90}
    before = [big]
    after = [big, {**_rule(81), "notes": "n" * 90}]
    lines, header = _render(before, after, attr_name="ingress", collection_kind="list")
    assert header is None
    assert any("+ ingress[1]" in line for line in lines)


def _create_cluster_change() -> Change:
    payload = json.loads((TESTDATA_DIR / "09_create_atlas_compact.json").read_text())
    for rc in payload["resource_changes"]:
        if rc["address"] == "module.cluster.mongodbatlas_advanced_cluster.this":
            return Change.model_validate(rc["change"])
    raise AssertionError("cluster change not found")


def _cluster_schema() -> ResourceSchema:
    return ResourceSchema.model_validate(
        json.loads((TESTDATA_DIR / "schemas/mongodbatlas_advanced_cluster.json").read_text())
    )


def test_create_nested_attr_uses_inline_hcl() -> None:
    change = _create_cluster_change()
    after = change.after or {}
    result = render_complex_value(
        None,
        after["replication_specs"],
        attr_name="replication_specs",
        resource_address="module.cluster.mongodbatlas_advanced_cluster.this",
        indent=_INDENT,
        terminal_width=_WIDE,
        config=ComplexRenderConfig(),
        change=change,
        schema=_cluster_schema(),
    )
    body = "\n".join(result.hcl_body_lines)
    assert "replication_specs = [" in body
    assert "instance_size" in body
    assert "replication_specs[0]" not in body


def _cluster_resize_change() -> Change:
    payload = json.loads((TESTDATA_DIR / "08_cluster_resize.json").read_text())
    return Change.model_validate(payload["resource_changes"][0]["change"])


def test_annex_guard_skips_computed_only_normalization() -> None:
    change = _cluster_resize_change()
    before = change.before or {}
    after = change.after or {}
    lookups = build_schema_lookups_from_index({})
    result = render_complex_value(
        before.get("advanced_configuration"),
        after.get("advanced_configuration"),
        attr_name="advanced_configuration",
        resource_address="module.cluster.mongodbatlas_advanced_cluster.this",
        indent=_INDENT,
        terminal_width=_WIDE,
        config=ComplexRenderConfig(),
        show_full_config_annex=True,
        change=change,
        computed_lookup=lookups.computed_at_path,
        provider="registry.terraform.io/mongodb/mongodbatlas",
        resource_type="mongodbatlas_advanced_cluster",
    )
    assert result.detail_block is None


def test_none_collection_kind_uses_list_matching() -> None:
    before = _ingress_rules(5)
    after = [before[0], _rule(3000), *before[1:]]
    lines, _ = _render(before, after, attr_name="ingress", collection_kind=None)
    assert any("ingress[1]" in line for line in lines)
