from __future__ import annotations

from pathlib import Path

import pytest

from tfdo._internal.output.apply_blockers import build_apply_blockers
from tfdo._internal.output.apply_display import (
    ApplyDisplayCliOverrides,
    ApplyDisplayOptions,
    format_elapsed_compact,
    parse_duration_seconds,
    resolve_apply_display,
)
from tfdo._internal.output.apply_renderer import (
    render_ci_completion_line,
    render_ci_final_summary,
    render_ci_heartbeat_line,
    render_completion_line,
    render_final_summary,
    render_live_section,
)
from tfdo._internal.output.apply_state import ApplyPhase, ApplyProgressState, ApplyResourceStatus, CompletionEmission
from tfdo._internal.output.models import Change, PlanOutput, ResourceAction, ResourceChange
from tfdo._internal.output.parser import parse_plan_file
from tfdo._internal.output.stream_models import ChangeCounts, ChangeSummaryEvent

CPA_AUTH = "module.gcp.module.cloud_provider_access[0].mongodbatlas_cloud_provider_access_authorization.this"
CPA_SETUP = "module.gcp.module.cloud_provider_access[0].mongodbatlas_cloud_provider_access_setup.this"
LOG_BUCKET = "module.gcp.module.log_integration[0].google_storage_bucket.atlas[0]"
LOG_IAM = 'module.gcp.module.log_integration[0].google_storage_bucket_iam_member.atlas["default"]'
LOG_INTEGRATION = "module.gcp.module.log_integration[0].mongodbatlas_log_integration.this[0]"
LOG_SLEEP = "module.gcp.module.log_integration[0].time_sleep.iam_propagation[0]"


def _state(addrs: list[tuple[str, ResourceAction]]) -> ApplyProgressState:
    plan = PlanOutput(
        format_version="1.2",
        errored=False,
        resource_changes=[
            ResourceChange(
                address=addr,
                mode="managed",
                type="t",
                name="n",
                change=Change(actions=_plan_actions(action)),
            )
            for addr, action in addrs
        ],
    )
    return ApplyProgressState(plan)


def _plan_actions(action: ResourceAction) -> list[str]:
    match action:
        case ResourceAction.REPLACE_DESTROY_FIRST:
            return ["delete", "create"]
        case _:
            return [action]


def test_render_completion_and_summary() -> None:
    state = _state([("aws_instance.web", ResourceAction.CREATE)])
    state.phase = ApplyPhase.DONE
    state.resources["aws_instance.web"].status = ApplyResourceStatus.COMPLETED
    state.terminal_summary = ChangeSummaryEvent(changes=ChangeCounts(add=1, operation="apply"))
    display = resolve_apply_display(ApplyDisplayOptions(), None, ApplyDisplayCliOverrides())
    line = render_completion_line(
        CompletionEmission("aws_instance.web", False, 3.0, "create"),
        addr_width=16,
    )
    assert "✅" in str(line)
    assert "created" in str(line)
    summary = render_final_summary(state, total_elapsed_s=48.0, display=display)
    assert any("Apply complete:" in str(part) for part in summary)
    assert any("added" in str(part) for part in summary)


def test_render_live_pending_blockers() -> None:
    state = _state(
        [
            ("aws_vpc.main", ResourceAction.CREATE),
            ("aws_instance.web", ResourceAction.CREATE),
        ]
    )
    state.phase = ApplyPhase.APPLYING
    state.blockers = {"aws_instance.web": frozenset({"aws_vpc.main"})}
    state.resources["aws_vpc.main"].status = ApplyResourceStatus.IN_PROGRESS
    state.resources["aws_vpc.main"].hook_action = "create"
    state.resources["aws_vpc.main"].started_at = 0.0
    display = resolve_apply_display(ApplyDisplayOptions(), None, ApplyDisplayCliOverrides())
    live = render_live_section(state, addr_width=20, display=display, now=130.0)
    assert live is not None
    text = str(live)
    assert "Apply: 0/2 resources" in text
    assert "waiting_on(aws_vpc.main)" in text


def test_render_live_pending_sort_and_waiting_on(apply_blockers_count_plan: Path) -> None:
    plan = parse_plan_file(apply_blockers_count_plan)
    blockers = build_apply_blockers(apply_blockers_count_plan)
    state = ApplyProgressState(plan, blockers)
    state.phase = ApplyPhase.APPLYING
    state.resources[CPA_SETUP].status = ApplyResourceStatus.IN_PROGRESS
    state.resources[CPA_SETUP].hook_action = "create"
    state.resources[CPA_SETUP].started_at = 0.0
    assert [resource.addr for resource in state.pending_resources_sorted()] == [
        LOG_BUCKET,
        LOG_IAM,
        LOG_INTEGRATION,
        CPA_AUTH,
        LOG_SLEEP,
    ]
    display = resolve_apply_display(ApplyDisplayOptions(), None, ApplyDisplayCliOverrides())
    live = render_live_section(state, addr_width=120, display=display, now=10.0)
    assert live is not None
    text = str(live)
    pending_section = text.split("── pending ──", maxsplit=1)[1]
    assert f"waiting_on({CPA_SETUP})" in pending_section
    assert f"waiting_on({LOG_BUCKET}" in pending_section
    assert f"waiting_on({LOG_SLEEP})" in pending_section


def test_ci_renderer_lines() -> None:
    display = resolve_apply_display(ApplyDisplayOptions(), None, ApplyDisplayCliOverrides())
    slow_line = render_ci_completion_line(
        CompletionEmission("aws_rds_instance.db", False, 720.0, "create"),
        display=display,
    )
    assert slow_line.startswith("apply: ✅")
    assert slow_line.endswith("🐌")
    assert format_elapsed_compact(18.0) == "18s"
    assert format_elapsed_compact(130.0) == "2m"
    with pytest.raises(ValueError, match="heartbeat_interval"):
        parse_duration_seconds("bad", key="heartbeat_interval")

    state = _state(
        [
            ("random_pet.alpha", ResourceAction.CREATE),
            ("random_pet.beta", ResourceAction.CREATE),
            ("local_file.gamma", ResourceAction.CREATE),
        ]
    )
    state.phase = ApplyPhase.APPLYING
    state.resources["random_pet.alpha"].status = ApplyResourceStatus.IN_PROGRESS
    state.resources["random_pet.alpha"].elapsed_seconds = 130.0
    state.resources["random_pet.beta"].status = ApplyResourceStatus.IN_PROGRESS
    state.resources["random_pet.beta"].elapsed_seconds = 18.0
    heartbeat = render_ci_heartbeat_line(state, display=display, now=1000.0)
    assert heartbeat is not None
    assert "in progress:" in heartbeat
    assert "pending: 1" in heartbeat
    assert "🐢 random_pet.alpha (2m)" in heartbeat

    state.phase = ApplyPhase.DONE
    state.resources["random_pet.alpha"].status = ApplyResourceStatus.COMPLETED
    state.terminal_summary = ChangeSummaryEvent(changes=ChangeCounts(add=1, operation="apply"))
    summary = render_ci_final_summary(state, total_elapsed_s=52.0)
    assert summary == ["apply: 1 ✅  total 52s", "apply: 🟢 1 added"]
