from __future__ import annotations

from tfdo._internal.output.attr_diff import AttrPrefix, compute_attr_lines
from tfdo._internal.output.create_filter import is_empty_create_value
from tfdo._internal.output.parser import parse_plan_file
from tfdo._internal.output.plan_filters import (
    filter_attr_lines,
    format_computed_delta_line,
    is_computed_only_drift_resource,
    is_computed_only_plan_delta,
)
from tfdo._internal.output.plan_render_input import build_attr_lines_by_addr
from tfdo._internal.output.testdata_paths import TESTDATA_DIR
from tfdo._internal.output.tree_builder import build_plan_tree


def _cluster_node(tree):
    for node in tree.root_resources:
        if node.type == "mongodbatlas_advanced_cluster":
            return node

    def walk(modules):
        for module in modules:
            for node in module.child_resources:
                if node.type == "mongodbatlas_advanced_cluster":
                    return node
            found = walk(module.child_modules)
            if found:
                return found
        return None

    return walk(tree.modules)


def test_cluster_resize_hides_computed_plan_deltas(fixture_schema_lookups) -> None:
    plan = parse_plan_file(TESTDATA_DIR / "08_cluster_resize.json")
    tree = build_plan_tree(plan)
    provider = "registry.terraform.io/mongodb/mongodbatlas"
    lookups = fixture_schema_lookups
    cluster = _cluster_node(tree)
    assert cluster is not None
    for name in ("connection_strings", "state_name", "config_server_type", "mongo_db_version"):
        assert is_computed_only_plan_delta(
            (name,),
            cluster.change,
            lookups.computed_at_path,
            provider=provider,
            resource_type=cluster.type,
        )


def test_is_empty_create_value() -> None:
    assert is_empty_create_value(None)
    assert is_empty_create_value("")
    assert is_empty_create_value([])
    assert is_empty_create_value({})
    assert not is_empty_create_value(False)
    assert not is_empty_create_value(90)


def test_filter_attr_lines_computed_expanded(fixture_schema_lookups) -> None:
    plan = parse_plan_file(TESTDATA_DIR / "08_cluster_resize.json")
    tree = build_plan_tree(plan)
    cluster = _cluster_node(tree)
    assert cluster is not None
    provider = "registry.terraform.io/mongodb/mongodbatlas"
    lines = compute_attr_lines(cluster.change, frozenset({"name", "project_id"}))
    compact = filter_attr_lines(
        lines,
        change=cluster.change,
        lookup=fixture_schema_lookups.computed_at_path,
        provider=provider,
        resource_type=cluster.type,
        show_computed_deltas=False,
    )
    assert "connection_strings" not in {line.name for line in compact if line.prefix}
    expanded = filter_attr_lines(
        lines,
        change=cluster.change,
        lookup=fixture_schema_lookups.computed_at_path,
        provider=provider,
        resource_type=cluster.type,
        show_computed_deltas=True,
    )
    conn = next(line for line in expanded if line.name.startswith("connection_strings"))
    assert conn.prefix == AttrPrefix.REMOVE
    assert "(computed, omitted from config)" in conn.name
    assert format_computed_delta_line("state_name", AttrPrefix.CHANGE).name.endswith("(computed, omitted from config)")


def test_cluster_resize_drift_filtering(fixture_schema_lookups) -> None:
    plan = parse_plan_file(TESTDATA_DIR / "08_cluster_resize.json")
    tree = build_plan_tree(plan)
    lookups = fixture_schema_lookups
    providers = {rc.address: rc.provider_name or "" for rc in plan.resource_drift}
    attr_lines = build_attr_lines_by_addr(
        tree,
        required_attrs=lookups.required_attrs,
        provider_by_addr=providers,
    ).drift
    visible = [
        node.address
        for node in tree.drift
        if not is_computed_only_drift_resource(
            node,
            attr_lines[node.address],
            lookups.computed_at_path,
            provider=providers[node.address],
        )
    ]
    assert visible == [
        "module.gcp.module.cloud_provider_access[0].mongodbatlas_cloud_provider_access_authorization.this"
    ]
    hidden = {node.address for node in tree.drift} - set(visible)
    assert "mongodbatlas_project.this" in hidden
    assert any("google_storage_bucket" in addr for addr in hidden)
