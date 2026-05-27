from __future__ import annotations

from tfdo._internal.output.parser import parse_plan_file
from tfdo._internal.output.plan_filters import is_computed_only_drift_resource, is_computed_only_plan_delta
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
