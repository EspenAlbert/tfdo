from __future__ import annotations

from pathlib import Path

import pytest

from tfdo._internal.output.attr_diff import compute_attr_lines
from tfdo._internal.output.display_path import replace_display_key
from tfdo._internal.output.models import Change, PlanOutput
from tfdo._internal.output.parser import parse_plan_file


def _change(plan: PlanOutput, address: str) -> Change:
    for rc in plan.resource_changes:
        if rc.address == address:
            return rc.change
    raise ValueError(f"missing resource: {address}")


def _names(lines: list) -> list[tuple[str, str | None]]:
    return [(line.name, line.prefix.value if line.prefix else None) for line in lines]


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
    ("before_sensitive", "after_sensitive", "key"),
    [
        ({"secret": True}, {}, "secret"),
        ({}, {"secret": True}, "secret"),
    ],
)
def test_sensitive_masks_values(
    before_sensitive: dict[str, object],
    after_sensitive: dict[str, object],
    key: str,
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
