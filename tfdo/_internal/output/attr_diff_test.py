from __future__ import annotations

import json
from pathlib import Path

import pytest

from tfdo._internal.output.attr_diff import AttrPrefix, compute_attr_lines
from tfdo._internal.output.display_path import replace_display_key
from tfdo._internal.output.models import Change, ChangeMarker, PlanOutput
from tfdo._internal.output.parser import parse_plan_file
from tfdo._internal.output.schema_lookup import resource_schema_required_attrs
from tfdo._internal.output.testdata_paths import TESTDATA_DIR
from tfdo._internal.schema.models import ResourceSchema

_CLUSTER_SCHEMA_PATH = TESTDATA_DIR / "schemas" / "mongodbatlas_advanced_cluster.json"


def _change(plan: PlanOutput, address: str) -> Change:
    for rc in plan.resource_changes:
        if rc.address == address:
            return rc.change
    raise ValueError(f"missing resource: {address}")


def _names(lines: list) -> list[tuple[str, str | None]]:
    return [(line.name, line.prefix or None) for line in lines]


def _context_names(lines: list) -> list[str]:
    return [line.name for line in lines if line.prefix is None]


def _cluster_change() -> Change:
    payload = json.loads((TESTDATA_DIR / "08_cluster_resize.json").read_text())
    return Change.model_validate(payload["resource_changes"][0]["change"])


def _cluster_required_from_schema() -> frozenset[str]:
    schema = ResourceSchema.model_validate(json.loads(_CLUSTER_SCHEMA_PATH.read_text()))
    return resource_schema_required_attrs(schema)


def test_create_hides_unknown_and_marks_user_set(create_flat_plan: Path) -> None:
    plan = parse_plan_file(create_flat_plan)
    lines = compute_attr_lines(_change(plan, "local_file.config"), frozenset({"filename"}))
    assert ("filename", None) in _names(lines)
    assert ("content", "+") not in _names(lines)
    assert ("file_permission", "+") in _names(lines)

    pet = compute_attr_lines(_change(plan, "random_pet.server"), frozenset())
    assert ("prefix", "+") in _names(pet)
    assert ("id", "+") not in _names(pet)


def test_update_changed_and_removed() -> None:
    change = Change(
        actions=["update"],
        before={"name": "a", "old_attr": "x", "drop": "gone"},
        after={"name": "a", "old_attr": "y"},
        after_unknown={},
    )
    lines = compute_attr_lines(change, frozenset({"name"}))
    assert _names(lines) == [("name", None), ("drop", "-"), ("old_attr", "~")]


def test_replace_top_level_from_fixture(update_plan: Path) -> None:
    plan = parse_plan_file(update_plan)
    lines = compute_attr_lines(_change(plan, "local_file.config"), frozenset({"filename"}))
    names = _names(lines)
    assert ("filename", None) in names
    assert ("content", "!") in names
    assert ("file_permission", "!") in names


def test_replace_multi_path_and_sort_order() -> None:
    change = Change(
        actions=["delete", "create"],
        before={"alpha": 1, "beta": 2, "gamma": 3, "trigger": "old"},
        after={"alpha": 1, "beta": 20, "gamma": 30, "trigger": "new"},
        replace_paths=[["trigger"]],
    )
    lines = compute_attr_lines(change, frozenset({"alpha"}))
    assert _names(lines) == [("alpha", None), ("trigger", "!"), ("beta", "~"), ("gamma", "~")]


def test_replace_nested_map_uses_parent_key() -> None:
    before: dict[str, object] = {"tags": {"Name": "old", "Env": "dev"}}
    after: dict[str, object] = {"tags": {"Name": "new", "Env": "dev"}}
    change = Change(
        actions=["delete", "create"],
        before=before,
        after=after,
        replace_paths=[["tags", "Name"]],
    )
    assert replace_display_key(["tags", "Name"], before, after) == "tags"
    assert _names(compute_attr_lines(change, frozenset())) == [("tags", "!")]


def test_destroy_required_context(destroy_plan: Path) -> None:
    plan = parse_plan_file(destroy_plan)
    lines = compute_attr_lines(_change(plan, "random_pet.db_name"), frozenset({"prefix"}))
    assert len(lines) == 1
    assert lines[0].name == "prefix"
    assert lines[0].prefix is None
    assert lines[0].old_value == "db"


@pytest.mark.parametrize(
    ("before_sensitive", "after_sensitive"),
    [
        ({"secret": True}, {}),
        ({}, {"secret": True}),
    ],
)
def test_sensitive_masks_values(
    before_sensitive: ChangeMarker,
    after_sensitive: ChangeMarker,
) -> None:
    change = Change(
        actions=["update"],
        before={"secret": "old"},
        after={"secret": "new"},
        before_sensitive=before_sensitive,
        after_sensitive=after_sensitive,
    )
    line = compute_attr_lines(change, frozenset())[0]
    assert line.is_sensitive
    assert line.old_value is None
    assert line.new_value is None


def test_replace_fixture_multi_resource(replace_plan: Path) -> None:
    plan = parse_plan_file(replace_plan)
    service = compute_attr_lines(_change(plan, "random_pet.service"), frozenset())
    assert ("length", "!") in _names(service)
    assert ("prefix", "!") in _names(service)
    assert ("separator", "!") in _names(service)

    token = compute_attr_lines(_change(plan, "random_string.token"), frozenset())
    assert ("length", "!") in _names(token)
    assert ("special", "!") in _names(token)


def test_update_required_context_with_full_after() -> None:
    lines = compute_attr_lines(_cluster_change(), _cluster_required_from_schema())
    assert _context_names(lines) == ["cluster_type", "name", "project_id"]


def test_update_required_context_with_config_only_after() -> None:
    change = _cluster_change()
    after = dict(change.after or {})
    for key in ("cluster_type", "name", "project_id"):
        after.pop(key, None)
    config_only = change.model_copy(update={"after": after})

    lines = compute_attr_lines(config_only, _cluster_required_from_schema())

    assert _context_names(lines) == ["cluster_type", "name", "project_id"]
    changed_names = {line.name for line in lines if line.prefix == AttrPrefix.CHANGE}
    assert "replication_specs" in changed_names
    assert "cluster_type" not in changed_names
    assert "name" not in changed_names
    assert "project_id" not in changed_names


def test_create_compact_hides_empty_top_level(create_atlas_compact_plan: Path) -> None:
    plan = parse_plan_file(create_atlas_compact_plan)
    project = _change(plan, "mongodbatlas_project.this")
    compact = {line.name for line in compute_attr_lines(project, frozenset({"name"}))}
    assert "tags" not in compact
    assert "limits" not in compact
    verbose = {line.name for line in compute_attr_lines(project, frozenset({"name"}), show_create_defaults=True)}
    assert "tags" in verbose

    cluster = _change(plan, "module.cluster.mongodbatlas_advanced_cluster.this")
    cluster_compact = {line.name for line in compute_attr_lines(cluster, frozenset({"name", "project_id"}))}
    assert "aws" not in cluster_compact


def test_update_changed_required_attr_shows_delta_not_context() -> None:
    change = _cluster_change()
    before = dict(change.before or {})
    after = dict(change.after or {})
    after["name"] = "renamed-cluster"
    renamed = change.model_copy(update={"before": before, "after": after})

    lines = compute_attr_lines(renamed, _cluster_required_from_schema())

    assert "name" not in _context_names(lines)
    name_line = next(line for line in lines if line.name == "name")
    assert name_line.prefix == AttrPrefix.CHANGE
    assert name_line.old_value == "example-cluster-name"
    assert name_line.new_value == "renamed-cluster"
