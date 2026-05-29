from tfdo._internal.output.apply_display import ApplyDisplayCliOverrides, ApplyDisplayOptions, resolve_apply_display
from tfdo._internal.output.apply_renderer import render_completion_line, render_final_summary, render_live_section
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
