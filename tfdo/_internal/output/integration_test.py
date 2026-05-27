from __future__ import annotations

import json

import pytest

from tfdo._internal.output.conftest import render_fixture
from tfdo._internal.output.structural_diff import DiffPrefix, apply_line_budget, compute_structural_diff
from tfdo._internal.output.testdata_paths import TESTDATA_DIR

FIXTURE_NAMES = (
    "01_create_flat",
    "02_create_modules",
    "03_update",
    "04_replace",
    "05_destroy",
    "06_outputs_only",
    "07_drift",
)


@pytest.mark.parametrize("basename", FIXTURE_NAMES)
def test_render_fixture(basename: str, capture_console, file_regression) -> None:
    rendered = render_fixture(TESTDATA_DIR / f"{basename}.json", capture_console)
    file_regression.check(rendered, basename=basename, extension=".txt")


def test_render_empty(empty_plan, capture_console, file_regression) -> None:
    rendered = render_fixture(None, capture_console, plan=empty_plan)
    file_regression.check(rendered, basename="empty", extension=".txt")


def test_render_create_atlas_compact(
    create_atlas_compact_plan, capture_console, fixture_schema_lookups, file_regression
) -> None:
    rendered = render_fixture(
        create_atlas_compact_plan,
        capture_console,
        schema_lookups=fixture_schema_lookups,
    )
    file_regression.check(rendered, basename="09_create_atlas_compact", extension=".txt")


def test_render_cluster_resize(cluster_resize_plan, capture_console, fixture_schema_lookups, file_regression) -> None:
    rendered = render_fixture(
        cluster_resize_plan,
        capture_console,
        schema_lookups=fixture_schema_lookups,
    )
    file_regression.check(rendered, basename="08_cluster_resize", extension=".txt")


def test_cluster_resize_structural_instance_size_paths(cluster_resize_plan) -> None:
    payload = json.loads(cluster_resize_plan.read_text())
    change = payload["resource_changes"][0]["change"]
    diff = compute_structural_diff(change["before"]["replication_specs"], change["after"]["replication_specs"])
    sizes = [
        line for line in diff if line.path and line.path[-1] == "instance_size" and line.prefix == DiffPrefix.CHANGE
    ]
    assert len(sizes) == 2


def test_apply_line_budget_truncates() -> None:
    diff = compute_structural_diff({"a": 1, "b": 2, "c": 3}, {"a": 2, "b": 3, "c": 4})
    result = apply_line_budget(diff, 1, budget=200)
    assert len(result.lines) == 2
    assert result.hidden_count == 2
