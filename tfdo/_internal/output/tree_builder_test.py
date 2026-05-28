from __future__ import annotations

from pathlib import Path

from tfdo._internal.output.models import Change, PlanOutput, ResourceAction, ResourceChange
from tfdo._internal.output.parser import parse_plan_file
from tfdo._internal.output.tree_builder import build_plan_tree


def _rc(
    address: str,
    actions: list[str],
    *,
    module_address: str | None = None,
) -> ResourceChange:
    return ResourceChange(
        address=address,
        mode="managed",
        type="local_file",
        name=address.rsplit(".", 1)[-1],
        module_address=module_address,
        change=Change(actions=actions),
    )


def _plan(*changes: ResourceChange) -> PlanOutput:
    return PlanOutput(format_version="1.2", errored=False, resource_changes=list(changes))


def test_build_flat_create(create_flat_plan: Path) -> None:
    plan = parse_plan_file(create_flat_plan)
    tree = build_plan_tree(plan)
    assert len(tree.root_resources) == 3
    assert tree.modules == []
    assert all(n.action == ResourceAction.CREATE for n in tree.root_resources)
    assert tree.output_changes == plan.output_changes


def test_build_modules_mixed_root(create_modules_plan: Path) -> None:
    tree = build_plan_tree(parse_plan_file(create_modules_plan))
    assert len(tree.root_resources) == 1
    assert tree.root_resources[0].address == "random_pet.project"
    assert len(tree.modules) == 1
    networking = tree.modules[0]
    assert networking.name == "networking"
    assert len(networking.child_resources) == 2
    assert len(networking.child_modules) == 1
    dns = networking.child_modules[0]
    assert dns.name == "dns"
    assert len(dns.child_resources) == 2
    dns_addrs = {n.address for n in dns.child_resources}
    assert dns_addrs == {
        "module.networking.module.dns.local_file.dns_record",
        "module.networking.module.dns.random_string.zone_suffix",
    }


def test_build_destroy_sort(destroy_plan: Path) -> None:
    tree = build_plan_tree(parse_plan_file(destroy_plan))
    assert [n.address for n in tree.root_resources] == [
        "local_file.db_config",
        "random_id.cluster_id",
        "random_pet.db_name",
        "random_string.db_password",
    ]
    assert all(n.action == ResourceAction.DELETE for n in tree.root_resources)


def test_sort_order_all_actions() -> None:
    tree = build_plan_tree(
        _plan(
            _rc("z_create", ["create"]),
            _rc("y_update", ["update"]),
            _rc("x_replace_dc", ["delete", "create"]),
            _rc("w_replace_cd", ["create", "delete"]),
            _rc("v_delete", ["delete"]),
        )
    )
    assert [n.address for n in tree.root_resources] == [
        "v_delete",
        "w_replace_cd",
        "x_replace_dc",
        "y_update",
        "z_create",
    ]


def test_chain_collapse_three_levels() -> None:
    tree = build_plan_tree(
        _plan(
            _rc(
                "module.a.module.b.module.c.local_file.leaf",
                ["create"],
                module_address="module.a.module.b.module.c",
            ),
        )
    )
    assert len(tree.modules) == 1
    assert tree.modules[0].name == "a > b > c"
    assert len(tree.modules[0].child_resources) == 1


def test_excludes_no_op_and_read(update_plan: Path) -> None:
    tree = build_plan_tree(parse_plan_file(update_plan))
    addrs = {n.address for n in tree.root_resources}
    assert "random_pet.app" not in addrs
    assert "local_file.config" in addrs

    read_tree = build_plan_tree(_plan(_rc("data.example", ["read"])))
    assert read_tree.root_resources == []


def test_drift_extraction(drift_plan: Path) -> None:
    plan = parse_plan_file(drift_plan)
    tree = build_plan_tree(plan)
    assert len(tree.drift) == 1
    assert tree.drift[0].address == "local_file.config"
    assert tree.drift[0].action == ResourceAction.DELETE
    assert len(tree.root_resources) == 1
    assert tree.root_resources[0].action == ResourceAction.CREATE
