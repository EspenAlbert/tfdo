import pytest

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
from tfdo._internal.output.stream_models import ChangeCounts, ChangeSummaryEvent


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
