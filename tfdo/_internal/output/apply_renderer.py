from __future__ import annotations

from rich.text import Text

from tfdo._internal.output.apply_display import (
    ResolvedApplyDisplay,
    _SlowTier,
    format_elapsed,
    slow_tier,
)
from tfdo._internal.output.apply_state import (
    ApplyPhase,
    ApplyProgressState,
    ApplyResourceState,
    ApplyResourceStatus,
    CompletionEmission,
)
from tfdo._internal.output.apply_verbs import display_verbs_for_hook_action
from tfdo._internal.output.models import ResourceAction
from tfdo._internal.output.stream_models import ChangeSummaryEvent, DiagnosticBody

_PENDING_SEPARATOR = "── pending ──"
_CHECK_OK = "✅"
_CHECK_FAIL = "❌"
_SLOW_EMOJI = "🐢"
_VERY_SLOW_EMOJI = "🐌"


def max_addr_width(state: ApplyProgressState) -> int:
    return max((len(addr) for addr in state.resources), default=0)


def render_completion_line(
    emission: CompletionEmission,
    *,
    addr_width: int,
) -> Text:
    marker = _CHECK_FAIL if emission.errored else _CHECK_OK
    verb = display_verbs_for_hook_action(emission.hook_action or "create").past
    duration = format_elapsed(emission.elapsed_seconds or 0)
    text = Text()
    text.append(f"{marker} ")
    text.append(emission.addr.ljust(addr_width))
    text.append(f"  {verb}  {duration}")
    return text


def render_live_section(
    state: ApplyProgressState,
    *,
    addr_width: int,
    display: ResolvedApplyDisplay,
    now: float,
) -> Text | None:
    if state.phase != ApplyPhase.APPLYING or state.total_count == 0:
        return None
    in_progress = [
        resource for resource in state.resources.values() if resource.status == ApplyResourceStatus.IN_PROGRESS
    ]
    pending = [resource for resource in state.resources.values() if resource.status == ApplyResourceStatus.PENDING]
    if not in_progress and not pending:
        return None

    text = Text()
    text.append(f"Apply: {state.completed_count}/{state.total_count} resources\n", style="bold")
    for resource in sorted(in_progress, key=lambda item: item.addr):
        text.append_text(_render_in_progress_row(resource, addr_width=addr_width, display=display, now=now))
        text.append("\n")
    if pending:
        text.append(f"\n{_PENDING_SEPARATOR}\n", style="dim")
        for resource in sorted(pending, key=lambda item: item.addr):
            text.append_text(_render_pending_row(state, resource, addr_width=addr_width))
            text.append("\n")
    return text


def render_final_summary(
    state: ApplyProgressState,
    *,
    total_elapsed_s: float,
    display: ResolvedApplyDisplay,
) -> list[Text | str]:
    success, failed = _outcome_counts(state)
    lines: list[Text | str] = []
    outcome = Text()
    outcome.append("Apply complete: ")
    if failed:
        outcome.append(f"{success} {_CHECK_OK}, {failed} {_CHECK_FAIL}  ")
    else:
        outcome.append(f"{success} {_CHECK_OK}  ")
    outcome.append(f"total {format_elapsed(total_elapsed_s)}")
    lines.append(outcome)

    breakdown = _breakdown_line(state)
    if breakdown:
        lines.append(breakdown)

    failed_lines = _failed_recap_lines(state)
    if failed_lines:
        lines.append("")
        lines.append("  Failed:")
        lines.extend(failed_lines)
    return lines


def _render_in_progress_row(
    resource: ApplyResourceState,
    *,
    addr_width: int,
    display: ResolvedApplyDisplay,
    now: float,
) -> Text:
    elapsed = _resource_elapsed(resource, now)
    tier = slow_tier(elapsed, display.slow_seconds, display.very_slow_seconds)
    verb = display_verbs_for_hook_action(resource.hook_action or "create").present
    text = Text()
    if tier is not _SlowTier.NORMAL:
        text.append(f"{_VERY_SLOW_EMOJI if tier is _SlowTier.VERY_SLOW else _SLOW_EMOJI} ")
    text.append(resource.addr.ljust(addr_width))
    elapsed_style = "red" if tier is _SlowTier.VERY_SLOW else "yellow" if tier is _SlowTier.SLOW else ""
    text.append(f"  {verb}...", style="cyan")
    text.append("  ")
    text.append(format_elapsed(elapsed), style=elapsed_style or "dim")
    return text


def _render_pending_row(state: ApplyProgressState, resource: ApplyResourceState, *, addr_width: int) -> Text:
    text = Text(resource.addr.ljust(addr_width), style="dim")
    blockers = state.active_blockers(resource.addr)
    if blockers:
        text.append(f"  waiting_on({', '.join(blockers)})", style="dim")
    return text


def _resource_elapsed(resource: ApplyResourceState, now: float) -> float:
    if resource.elapsed_seconds is not None:
        return resource.elapsed_seconds
    if resource.started_at is not None:
        return now - resource.started_at
    return 0.0


def _outcome_counts(state: ApplyProgressState) -> tuple[int, int]:
    success = sum(
        1
        for addr, resource in state.resources.items()
        if resource.status == ApplyResourceStatus.COMPLETED and state.counts_toward_completed(addr)
    )
    failed = sum(1 for resource in state.resources.values() if resource.status == ApplyResourceStatus.ERRORED)
    return success, failed


def _breakdown_line(state: ApplyProgressState) -> Text | None:
    summary = state.terminal_summary
    if summary and summary.changes:
        return _breakdown_from_changes(summary)
    return _breakdown_from_resources(state)


def _breakdown_from_changes(summary: ChangeSummaryEvent) -> Text | None:
    changes = summary.changes
    if changes is None:
        return None
    parts: list[tuple[str, int]] = []
    if changes.add:
        parts.append(("🟢", changes.add))
    if changes.change:
        parts.append(("🟡", changes.change))
    if changes.remove:
        parts.append(("🔴", changes.remove))
    if not parts:
        return None
    text = Text("  ")
    labels = []
    for emoji, count in parts:
        label = _count_label(emoji, count)
        if label:
            labels.append(label)
    text.append(", ".join(labels))
    return text


def _breakdown_from_resources(state: ApplyProgressState) -> Text | None:
    counts = {"add": 0, "change": 0, "remove": 0}
    for addr, resource in state.resources.items():
        if resource.status != ApplyResourceStatus.COMPLETED or not state.counts_toward_completed(addr):
            continue
        _accumulate_plan_action(counts, resource.plan_action)
    parts = [
        _count_label("🟢", counts["add"]),
        _count_label("🟡", counts["change"]),
        _count_label("🔴", counts["remove"]),
    ]
    parts = [part for part in parts if part]
    if not parts:
        return None
    return Text("  " + ", ".join(parts))


def _accumulate_plan_action(counts: dict[str, int], action: ResourceAction) -> None:
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


def _count_label(emoji: str, count: int) -> str:
    if not count:
        return ""
    match emoji:
        case "🟢":
            return f"{emoji} {count} added"
        case "🟡":
            return f"{emoji} {count} changed"
        case "🔴":
            return f"{emoji} {count} destroyed"
        case _:
            return ""


def _failed_recap_lines(state: ApplyProgressState) -> list[Text]:
    lines: list[Text] = []
    for resource in sorted(
        (item for item in state.resources.values() if item.status == ApplyResourceStatus.ERRORED),
        key=lambda item: item.addr,
    ):
        lines.append(_failed_recap_line(resource))
    return lines


def _failed_recap_line(resource: ApplyResourceState) -> Text:
    text = Text(f"  {_CHECK_FAIL} {resource.addr}  ")
    if resource.diagnostic:
        text.append_text(_diagnostic_recap(resource.diagnostic))
    return text


def _diagnostic_recap(diag: DiagnosticBody) -> Text:
    summary = diag.summary
    for prefix in ("Error: ", "Error "):
        if summary.startswith(prefix):
            summary = summary[len(prefix) :]
            break
    text = Text(f"Error: {summary}")
    if diag.source_range:
        text.append(f" ({diag.source_range.filename}:{diag.source_range.start.line})")
    return text
