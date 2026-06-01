from __future__ import annotations

from pathlib import Path

from tfdo._internal.config.enums import LifecycleCommand
from tfdo._internal.output.apply_state import ApplyProgressState
from tfdo._internal.output.parser import parse_plan_file
from tfdo._internal.output.stream_models import ChangeCounts, ChangeSummaryEvent
from tfdo._internal.output.testdata_paths import TESTDATA_DIR
from tfdo._internal.output.tree_builder import build_plan_tree
from tfdo._internal.run.run_dir_summary import (
    FAILURE_LABEL,
    build_run_dir_summary,
    output_change_count_from_plan_tree,
    resource_counts_from_apply_state,
    resource_counts_from_change_counts,
    resource_counts_from_plan_tree,
    skipped_run_dir_summary,
)
from tfdo._internal.settings import TfDoSettings


def test_build_run_dir_summary_sets_fail_label() -> None:
    summary = build_run_dir_summary(
        run_dir="envs/dev/app",
        command=LifecycleCommand.PLAN,
        exit_code=1,
        skipped=False,
        duration_s=1.5,
    )
    assert summary.failure_label == FAILURE_LABEL
    assert summary.command == "plan"


def test_build_run_dir_summary_plan_fields_only_for_plan() -> None:
    summary = build_run_dir_summary(
        run_dir="envs/dev/app",
        command=LifecycleCommand.APPLY,
        exit_code=0,
        skipped=False,
        duration_s=2.0,
        resource_counts=resource_counts_from_change_counts(ChangeCounts(add=1, operation="apply")),
        output_change_count=3,
        has_applyable_changes=True,
    )
    assert summary.resource_counts is not None
    assert summary.resource_counts.add == 1
    assert summary.output_change_count == 3
    assert summary.has_applyable_changes is True
    assert summary.failure_label is None


def test_skipped_run_dir_summary() -> None:
    summary = skipped_run_dir_summary("envs/dev/app", LifecycleCommand.PLAN, 1)
    assert summary.skipped
    assert summary.duration_s == 0.0
    assert summary.resource_counts is None


def test_resource_counts_from_plan_tree() -> None:
    plan = parse_plan_file(TESTDATA_DIR / "01_create_flat.json")
    tree = build_plan_tree(plan)
    counts = resource_counts_from_plan_tree(tree)
    assert counts.add == 3
    assert counts.change == 0
    assert output_change_count_from_plan_tree(tree) == 2


def test_resource_counts_from_apply_ndjson() -> None:
    ndjson = (
        Path(__file__).resolve().parents[1] / "output" / "apply_stream_handler_regression_test" / "all_success.ndjson"
    )
    plan = parse_plan_file(TESTDATA_DIR / "01_create_flat.json")
    state = ApplyProgressState(plan, settings=TfDoSettings(work_dir=Path("/tmp/tfdo-test")))
    for line in ndjson.read_text().splitlines():
        if line.strip():
            state.feed_line(line + "\n")
    counts = resource_counts_from_apply_state(state)
    assert counts is not None
    assert counts.add == 3
    assert counts.change == 0
    assert counts.destroy == 0


def test_resource_counts_from_terminal_summary() -> None:
    plan = parse_plan_file(TESTDATA_DIR / "01_create_flat.json")
    state = ApplyProgressState(plan, settings=TfDoSettings(work_dir=Path("/tmp/tfdo-test")))
    state.terminal_summary = ChangeSummaryEvent(changes=ChangeCounts(add=2, change=1, remove=1, operation="apply"))
    counts = resource_counts_from_apply_state(state)
    assert counts == resource_counts_from_change_counts(ChangeCounts(add=2, change=1, remove=1))
