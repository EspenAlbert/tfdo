from __future__ import annotations

from typing import NamedTuple

from pydantic import BaseModel

from tfdo._internal.config.enums import LifecycleCommand
from tfdo._internal.output.apply_state import ApplyProgressState, ApplyResourceStatus
from tfdo._internal.output.models import ResourceAction
from tfdo._internal.output.stream_models import ChangeCounts
from tfdo._internal.output.tree_builder import PlanTree

FAILURE_LABEL = "FAIL"


class ResourceActionCounts(NamedTuple):
    add: int = 0
    change: int = 0
    destroy: int = 0
    replace: int = 0


class RunDirSummary(BaseModel):
    run_dir: str
    command: str
    exit_code: int
    skipped: bool = False
    duration_s: float = 0.0
    resource_counts: ResourceActionCounts | None = None
    output_change_count: int | None = None
    has_applyable_changes: bool | None = None
    failure_label: str | None = None


def build_run_dir_summary(
    *,
    run_dir: str,
    command: str | LifecycleCommand,
    exit_code: int,
    skipped: bool,
    duration_s: float,
    resource_counts: ResourceActionCounts | None = None,
    output_change_count: int | None = None,
    has_applyable_changes: bool | None = None,
) -> RunDirSummary:
    cmd = command.value if isinstance(command, LifecycleCommand) else command
    failure_label = FAILURE_LABEL if exit_code != 0 and resource_counts is None else None
    return RunDirSummary(
        run_dir=run_dir,
        command=cmd,
        exit_code=exit_code,
        skipped=skipped,
        duration_s=duration_s,
        resource_counts=resource_counts,
        output_change_count=output_change_count,
        has_applyable_changes=has_applyable_changes,
        failure_label=failure_label,
    )


def skipped_run_dir_summary(
    run_dir: str,
    command: str | LifecycleCommand,
    exit_code: int,
    *,
    skipped: bool = True,
) -> RunDirSummary:
    return build_run_dir_summary(
        run_dir=run_dir,
        command=command,
        exit_code=exit_code,
        skipped=skipped,
        duration_s=0.0,
    )


def resource_counts_from_plan_tree(tree: PlanTree) -> ResourceActionCounts:
    from tfdo._internal.output.plan_renderer import _action_counts

    counts = _action_counts(tree)
    return ResourceActionCounts(
        add=counts.add,
        change=counts.change,
        destroy=counts.destroy,
        replace=counts.replace,
    )


def output_change_count_from_plan_tree(tree: PlanTree) -> int | None:
    from tfdo._internal.output.plan_renderer import _output_action_counts

    new, changed, deleted = _output_action_counts(tree.output_changes)
    total = new + changed + deleted
    return total or None


def resource_counts_from_change_counts(changes: ChangeCounts) -> ResourceActionCounts | None:
    if not (changes.add or changes.change or changes.remove):
        return None
    return ResourceActionCounts(
        add=changes.add,
        change=changes.change,
        destroy=changes.remove,
        replace=0,
    )


def _accumulate_resource_action(counts: dict[str, int], action: ResourceAction) -> None:
    match action:
        case ResourceAction.CREATE:
            counts["add"] += 1
        case ResourceAction.UPDATE:
            counts["change"] += 1
        case ResourceAction.DELETE:
            counts["remove"] += 1
        case ResourceAction.REPLACE_DESTROY_FIRST | ResourceAction.REPLACE_CREATE_FIRST:
            counts["add"] += 1
            counts["remove"] += 1


def resource_counts_from_apply_state(state: ApplyProgressState) -> ResourceActionCounts | None:
    summary = state.terminal_summary
    if summary and summary.changes is not None:
        return resource_counts_from_change_counts(summary.changes)
    counts = {"add": 0, "change": 0, "remove": 0}
    for resource in state.resources.values():
        if resource.status != ApplyResourceStatus.COMPLETED or not state.counts_toward_completed(resource.addr):
            continue
        _accumulate_resource_action(counts, resource.plan_action)
    if not any(counts.values()):
        return None
    return ResourceActionCounts(
        add=counts["add"],
        change=counts["change"],
        destroy=counts["remove"],
        replace=0,
    )
