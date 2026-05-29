from __future__ import annotations

from pathlib import Path

from tfdo._internal.output.apply_state import (
    PRE_APPLY_REFRESH_COMPLETE,
    PRE_APPLY_REFRESH_START,
    ApplyPhase,
    ApplyProgressState,
    ApplyResourceStatus,
    plan_from_planned_changes,
    seed_apply_addrs,
)
from tfdo._internal.output.models import Change, PlanOutput, ResourceAction, ResourceChange
from tfdo._internal.output.parser import parse_plan_file

APPLY_PROGRESS_DIR = Path(__file__).resolve().parents[4] / "00_debug" / "12_apply_progress"


def _fixture(name: str) -> Path:
    return APPLY_PROGRESS_DIR / name


def _load_lines(path: Path) -> list[str]:
    return [line for line in path.read_text().splitlines() if line.strip()]


def _replay(state: ApplyProgressState, lines: list[str]) -> None:
    for line in lines:
        state.feed_line(line + "\n")
    state.flush()


def _inline_plan(addrs: list[tuple[str, list[str]]]) -> PlanOutput:
    return PlanOutput(
        format_version="1.2",
        errored=False,
        resource_changes=[
            ResourceChange(
                address=addr,
                mode="managed",
                type="t",
                name="n",
                change=Change(actions=actions),
            )
            for addr, actions in addrs
        ],
    )


def test_apply_all_success(create_flat_plan: Path) -> None:
    path = _fixture("apply_all_success.ndjson")
    state = ApplyProgressState(parse_plan_file(create_flat_plan))
    _replay(state, _load_lines(path))
    assert state.phase == ApplyPhase.DONE
    assert all(r.status == ApplyResourceStatus.COMPLETED for r in state.resources.values())
    assert state.completed_count == state.total_count == 3
    assert state.terminal_summary and state.terminal_summary.changes
    assert state.terminal_summary.changes.operation == "apply"


def test_apply_validation_failed() -> None:
    plan = _inline_plan(
        [
            ("random_pet.first", ["create"]),
            ("local_file.second", ["create"]),
        ]
    )
    path = _fixture("apply_validation_failed.ndjson")
    state = ApplyProgressState(plan)
    _replay(state, _load_lines(path))
    assert state.resources["random_pet.first"].status == ApplyResourceStatus.COMPLETED
    second = state.resources["local_file.second"]
    assert second.status == ApplyResourceStatus.ERRORED
    assert second.diagnostic is not None
    assert state.terminal_summary is None
    assert state.phase != ApplyPhase.DONE


def test_provision_local_exec() -> None:
    plan = _inline_plan([("local_file.config", ["create"])])
    path = _fixture("provision_local_exec.ndjson")
    state = ApplyProgressState(plan)
    _replay(state, _load_lines(path))
    assert state.resources["local_file.config"].status == ApplyResourceStatus.COMPLETED
    assert state.drain_provision_logs()


def test_pre_apply_refresh_from_live() -> None:
    lines = _load_lines(_fixture("live_privatelink.ndjson"))
    plan = plan_from_planned_changes(lines)
    state = ApplyProgressState(plan)
    prefix = lines[
        : lines.index(
            next(line for line in lines if '"type":"change_summary"' in line and '"operation":"plan"' in line)
        )
        + 1
    ]
    _replay(state, prefix)
    assert state.drain_pre_apply_logs() == [PRE_APPLY_REFRESH_START, PRE_APPLY_REFRESH_COMPLETE]


def test_minimal_fixture_no_pre_apply_logs(create_flat_plan: Path) -> None:
    path = _fixture("apply_all_success.ndjson")
    state = ApplyProgressState(parse_plan_file(create_flat_plan))
    _replay(state, _load_lines(path))
    assert state.drain_pre_apply_logs() == []


def test_plan_from_planned_changes() -> None:
    lines = _load_lines(_fixture("live_privatelink.ndjson"))
    plan = plan_from_planned_changes(lines)
    assert len(seed_apply_addrs(plan)) >= 2
    assert all(rc.change.action() != ResourceAction.READ for rc in plan.resource_changes)


def test_destroy_saved_plan(destroy_plan: Path) -> None:
    path = _fixture("apply_destroy_saved_plan.ndjson")
    state = ApplyProgressState(parse_plan_file(destroy_plan))
    _replay(state, _load_lines(path))
    assert all(r.plan_action == ResourceAction.DELETE for r in state.resources.values())
    assert state.terminal_summary and state.terminal_summary.changes
    assert state.terminal_summary.changes.remove >= 1


def test_live_privatelink_partial() -> None:
    lines = _load_lines(_fixture("live_privatelink.ndjson"))
    state = ApplyProgressState(plan_from_planned_changes(lines))
    _replay(state, lines)
    errored = [a for a, r in state.resources.items() if r.status == ApplyResourceStatus.ERRORED]
    assert len(errored) >= 2
    assert state.phase != ApplyPhase.DONE
    assert state.terminal_summary is None
