from __future__ import annotations

import json
from pathlib import Path

from tfdo._internal.output.apply_state import (
    PRE_APPLY_REFRESH_COMPLETE,
    PRE_APPLY_REFRESH_START,
    ApplyPhase,
    ApplyProgressState,
    ApplyResourceStatus,
    plan_from_planned_changes,
    plan_has_applyable_changes,
    seed_apply_addrs,
)
from tfdo._internal.output.models import Change, PlanOutput, ResourceAction, ResourceChange
from tfdo._internal.output.parser import parse_plan_file
from tfdo._internal.output.testdata_paths import load_apply_progress_lines


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


def test_plan_has_applyable_changes_empty(empty_plan: PlanOutput) -> None:
    assert not plan_has_applyable_changes(empty_plan)


def test_plan_has_applyable_changes_outputs_only(outputs_only_plan: Path) -> None:
    plan = parse_plan_file(outputs_only_plan)
    assert plan_has_applyable_changes(plan)


def test_plan_has_applyable_changes_create(drift_plan: Path) -> None:
    plan = parse_plan_file(drift_plan)
    assert plan_has_applyable_changes(plan)


def test_plan_has_applyable_changes_drift_only_no_op() -> None:
    plan = PlanOutput(
        format_version="1.2",
        errored=False,
        applyable=False,
        resource_changes=[
            ResourceChange(
                address="local_file.config",
                mode="managed",
                type="local_file",
                name="config",
                change=Change(actions=["no-op"]),
            )
        ],
        resource_drift=[
            ResourceChange(
                address="local_file.config",
                mode="managed",
                type="local_file",
                name="config",
                change=Change(actions=["delete"]),
            )
        ],
    )
    assert not plan_has_applyable_changes(plan)


def test_plan_has_applyable_changes_respects_applyable() -> None:
    plan = PlanOutput(format_version="1.2", errored=False, applyable=True)
    assert plan_has_applyable_changes(plan)
    plan.applyable = False
    assert not plan_has_applyable_changes(plan)


def test_apply_all_success(create_flat_plan: Path) -> None:
    state = ApplyProgressState(parse_plan_file(create_flat_plan))
    _replay(state, load_apply_progress_lines("apply_all_success.ndjson"))
    assert state.phase == ApplyPhase.DONE
    assert all(r.status == ApplyResourceStatus.COMPLETED for r in state.resources.values())
    assert state.completed_count == state.total_count == 3
    assert state.terminal_summary and state.terminal_summary.changes
    assert state.terminal_summary.changes.operation == "apply"
    assert state.resolved_output_values() == {
        "config_path": "./output/app.conf",
        "server_name": "web-pure-elk",
    }


def test_apply_validation_failed() -> None:
    plan = _inline_plan(
        [
            ("random_pet.first", ["create"]),
            ("local_file.second", ["create"]),
        ]
    )
    state = ApplyProgressState(plan)
    _replay(state, load_apply_progress_lines("apply_validation_failed.ndjson"))
    assert state.resources["random_pet.first"].status == ApplyResourceStatus.COMPLETED
    second = state.resources["local_file.second"]
    assert second.status == ApplyResourceStatus.ERRORED
    assert second.diagnostic is not None
    assert state.terminal_summary is None
    assert state.phase != ApplyPhase.DONE


def test_provision_local_exec() -> None:
    plan = _inline_plan([("local_file.config", ["create"])])
    state = ApplyProgressState(plan)
    _replay(state, load_apply_progress_lines("provision_local_exec.ndjson"))
    assert state.resources["local_file.config"].status == ApplyResourceStatus.COMPLETED
    assert state.drain_provision_logs()


def test_pre_apply_refresh_logs() -> None:
    lines = load_apply_progress_lines("pre_apply_refresh.ndjson")
    state = ApplyProgressState(_inline_plan([("null_resource.one", ["create"])]))
    _replay(state, lines)
    assert state.drain_pre_apply_logs() == [PRE_APPLY_REFRESH_START, PRE_APPLY_REFRESH_COMPLETE]


def test_minimal_fixture_no_pre_apply_logs(create_flat_plan: Path) -> None:
    state = ApplyProgressState(parse_plan_file(create_flat_plan))
    _replay(state, load_apply_progress_lines("apply_all_success.ndjson"))
    assert state.drain_pre_apply_logs() == []


def test_plan_from_planned_changes() -> None:
    lines = load_apply_progress_lines("apply_all_success.ndjson")
    plan = plan_from_planned_changes(lines)
    assert len(seed_apply_addrs(plan)) == 3
    assert all(rc.change.action() != ResourceAction.READ for rc in plan.resource_changes)


def test_post_apply_object_output_type_captured() -> None:
    object_type = ["object", {"phase_a_rotation_rfc3339": "string"}]
    value = {"phase_a_rotation_rfc3339": "2026-01-01T00:00:00Z"}
    lines = [
        '{"type":"change_summary","changes":{"operation":"apply","add":0,"change":0,"remove":0}}',
        json.dumps(
            {
                "type": "outputs",
                "outputs": {
                    "rotation_schedule": {"sensitive": False, "type": object_type, "value": value},
                },
            }
        ),
    ]
    state = ApplyProgressState(_inline_plan([]))
    _replay(state, lines)
    assert state.post_apply_outputs is not None
    assert state.post_apply_outputs["rotation_schedule"].type == object_type
    assert state.resolved_output_values() == {"rotation_schedule": value}


def test_plan_phase_outputs_ignored() -> None:
    lines = [
        '{"type":"change_summary","changes":{"operation":"plan","add":1,"change":0,"remove":0}}',
        '{"type":"outputs","outputs":{"example":{"sensitive":false,"action":"create"}}}',
    ]
    state = ApplyProgressState(_inline_plan([("null_resource.one", ["create"])]))
    _replay(state, lines)
    assert state.post_apply_outputs is None
    assert not state.post_apply_outputs_received


def test_destroy_saved_plan(destroy_plan: Path) -> None:
    state = ApplyProgressState(parse_plan_file(destroy_plan))
    _replay(state, load_apply_progress_lines("apply_destroy_saved_plan.ndjson"))
    assert all(r.plan_action == ResourceAction.DELETE for r in state.resources.values())
    assert state.terminal_summary and state.terminal_summary.changes
    assert state.terminal_summary.changes.remove >= 1


def test_destroy_empty_outputs_skips_values(destroy_plan: Path) -> None:
    state = ApplyProgressState(parse_plan_file(destroy_plan))
    _replay(state, load_apply_progress_lines("apply_destroy_saved_plan.ndjson"))
    assert state.post_apply_outputs_received
    assert state.resolved_output_values() is None


def test_parallel_apply_errors_partial() -> None:
    lines = load_apply_progress_lines("parallel_apply_errors.ndjson")
    state = ApplyProgressState(plan_from_planned_changes(lines))
    _replay(state, lines)
    errored = [a for a, r in state.resources.items() if r.status == ApplyResourceStatus.ERRORED]
    assert errored == [
        'module.example["east"].null_resource.app',
        'module.example["west"].null_resource.app',
    ]
    assert state.phase != ApplyPhase.DONE
    assert state.terminal_summary is None


def test_replace_delete_create_emits_two_completions() -> None:
    lines = [
        '{"type":"planned_change","change":{"resource":{"addr":"module.a.aws_instance.web"},"action":"replace"}}',
        '{"type":"apply_start","hook":{"resource":{"addr":"module.a.aws_instance.web"},"action":"delete"}}',
        '{"type":"apply_complete","hook":{"resource":{"addr":"module.a.aws_instance.web"},"action":"delete","elapsed_seconds":2}}',
        '{"type":"apply_start","hook":{"resource":{"addr":"module.a.aws_instance.web"},"action":"create"}}',
        '{"type":"apply_complete","hook":{"resource":{"addr":"module.a.aws_instance.web"},"action":"create","elapsed_seconds":4}}',
    ]
    state = ApplyProgressState(plan_from_planned_changes(lines))
    for line in lines:
        state.ingest_line(line)
    state.flush()
    drained: list[tuple[str | None, bool]] = []
    while batch := state.drain_completion_emissions():
        drained.extend((item.hook_action, item.errored) for item in batch)
    assert drained == [("delete", False), ("create", False)]
    assert state.completed_count == 1
