from __future__ import annotations

from rich.text import Text

from tfdo._internal.output.apply_display import (
    ResolvedApplyDisplay,
    _SlowTier,
    format_elapsed,
    format_elapsed_compact,
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
from tfdo._internal.output.count_phrases import apply_past_phrase
from tfdo._internal.output.models import ResourceAction
from tfdo._internal.output.stream_models import ChangeSummaryEvent, DiagnosticBody

_PENDING_SEPARATOR = "── pending ──"
_CHECK_OK = "✅"
_CHECK_FAIL = "❌"
_SLOW_EMOJI = "🐢"
_VERY_SLOW_EMOJI = "🐌"
_APPLY_PREFIX = "apply: "
_IN_PROGRESS_PREFIX = "in progress: "


def scrollback_run_dir_prefix(run_dir_key: str) -> str:
    if not run_dir_key:
        return ""
    return f"[{run_dir_key}] "


def max_addr_width(state: ApplyProgressState) -> int:
    return max((len(addr) for addr in state.resources), default=0)


def render_completion_line(
    emission: CompletionEmission,
    *,
    addr_width: int,
    run_dir_key: str = "",
) -> Text:
    marker = _CHECK_FAIL if emission.errored else _CHECK_OK
    verb = display_verbs_for_hook_action(emission.hook_action or "create").past
    duration = format_elapsed(emission.elapsed_seconds or 0)
    text = Text()
    if run_dir_key:
        text.append(scrollback_run_dir_prefix(run_dir_key))
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
    pending = state.pending_resources_sorted()
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


def render_ci_completion_line(
    emission: CompletionEmission,
    *,
    display: ResolvedApplyDisplay,
    diagnostic: DiagnosticBody | None = None,
    run_dir_key: str = "",
) -> str:
    marker = _CHECK_FAIL if emission.errored else _CHECK_OK
    verb = display_verbs_for_hook_action(emission.hook_action or "create").past
    duration = format_elapsed(emission.elapsed_seconds or 0)
    tier = slow_tier(emission.elapsed_seconds or 0, display.slow_seconds, display.very_slow_seconds)
    slow_suffix = ""
    match tier:
        case _SlowTier.VERY_SLOW:
            slow_suffix = f" {_VERY_SLOW_EMOJI}"
        case _SlowTier.SLOW:
            slow_suffix = f" {_SLOW_EMOJI}"
    line = f"{scrollback_run_dir_prefix(run_dir_key)}{_APPLY_PREFIX}{marker} {emission.addr} {verb} {duration}{slow_suffix}"
    if emission.errored and diagnostic:
        line += f" | {_diagnostic_recap_plain(diagnostic)}"
    return line


def render_ci_heartbeat_line(
    state: ApplyProgressState,
    *,
    display: ResolvedApplyDisplay,
    now: float,
) -> str | None:
    in_progress = [
        resource for resource in state.resources.values() if resource.status == ApplyResourceStatus.IN_PROGRESS
    ]
    pending_count = sum(1 for resource in state.resources.values() if resource.status == ApplyResourceStatus.PENDING)
    if not in_progress:
        return None
    segments = [
        _heartbeat_resource_segment(resource, display=display, now=now)
        for resource in sorted(in_progress, key=lambda item: item.addr)
    ]
    line = f"{_IN_PROGRESS_PREFIX}{', '.join(segments)}"
    if pending_count:
        line += f" | pending: {pending_count}"
    return line


def render_ci_final_summary(
    state: ApplyProgressState,
    *,
    total_elapsed_s: float,
    run_dir_key: str = "",
) -> list[str]:
    dir_prefix = scrollback_run_dir_prefix(run_dir_key)
    success, failed = _outcome_counts(state)
    if failed:
        outcome = (
            f"{dir_prefix}{_APPLY_PREFIX}{success} {_CHECK_OK}, {failed} {_CHECK_FAIL}  "
            f"total {format_elapsed(total_elapsed_s)}"
        )
    else:
        outcome = f"{dir_prefix}{_APPLY_PREFIX}{success} {_CHECK_OK}  total {format_elapsed(total_elapsed_s)}"
    lines = [outcome]
    breakdown = _breakdown_plain(state)
    if breakdown:
        lines.append(f"{dir_prefix}{_APPLY_PREFIX}{breakdown}")
    return lines


def render_final_summary(
    state: ApplyProgressState,
    *,
    total_elapsed_s: float,
    display: ResolvedApplyDisplay,
    run_dir_key: str = "",
) -> list[Text | str]:
    success, failed = _outcome_counts(state)
    lines: list[Text | str] = []
    outcome = Text()
    if run_dir_key:
        outcome.append(scrollback_run_dir_prefix(run_dir_key))
    outcome.append("Apply complete: ")
    if failed:
        outcome.append(f"{success} {_CHECK_OK}, {failed} {_CHECK_FAIL}  ")
    else:
        outcome.append(f"{success} {_CHECK_OK}  ")
    outcome.append(f"total {format_elapsed(total_elapsed_s)}")
    lines.append(outcome)

    breakdown = _breakdown_line(state)
    if breakdown:
        if run_dir_key:
            prefixed = Text()
            prefixed.append(scrollback_run_dir_prefix(run_dir_key))
            prefixed.append_text(breakdown)
            lines.append(prefixed)
        else:
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
        label = apply_past_phrase(emoji, count)
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
        apply_past_phrase("🟢", counts["add"]),
        apply_past_phrase("🟡", counts["change"]),
        apply_past_phrase("🔴", counts["remove"]),
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
    return Text(_diagnostic_recap_plain(diag))


def _diagnostic_recap_plain(diag: DiagnosticBody) -> str:
    summary = diag.summary
    for prefix in ("Error: ", "Error "):
        if summary.startswith(prefix):
            summary = summary[len(prefix) :]
            break
    text = f"Error: {summary}"
    if diag.source_range:
        text += f" ({diag.source_range.filename}:{diag.source_range.start.line})"
    return text


def _heartbeat_resource_segment(
    resource: ApplyResourceState,
    *,
    display: ResolvedApplyDisplay,
    now: float,
) -> str:
    elapsed = _resource_elapsed(resource, now)
    tier = slow_tier(elapsed, display.slow_seconds, display.very_slow_seconds)
    prefix = ""
    match tier:
        case _SlowTier.VERY_SLOW:
            prefix = f"{_VERY_SLOW_EMOJI} "
        case _SlowTier.SLOW:
            prefix = f"{_SLOW_EMOJI} "
    return f"{prefix}{resource.addr} ({format_elapsed_compact(elapsed)})"


def _breakdown_plain(state: ApplyProgressState) -> str | None:
    summary = state.terminal_summary
    if summary and summary.changes:
        return _breakdown_plain_from_changes(summary)
    return _breakdown_plain_from_resources(state)


def _breakdown_plain_from_changes(summary: ChangeSummaryEvent) -> str | None:
    changes = summary.changes
    if changes is None:
        return None
    parts: list[str] = []
    if changes.add:
        parts.append(apply_past_phrase("🟢", changes.add))
    if changes.change:
        parts.append(apply_past_phrase("🟡", changes.change))
    if changes.remove:
        parts.append(apply_past_phrase("🔴", changes.remove))
    parts = [part for part in parts if part]
    if not parts:
        return None
    return ", ".join(parts)


def _breakdown_plain_from_resources(state: ApplyProgressState) -> str | None:
    counts = {"add": 0, "change": 0, "remove": 0}
    for addr, resource in state.resources.items():
        if resource.status != ApplyResourceStatus.COMPLETED or not state.counts_toward_completed(addr):
            continue
        _accumulate_plan_action(counts, resource.plan_action)
    parts = [
        apply_past_phrase("🟢", counts["add"]),
        apply_past_phrase("🟡", counts["change"]),
        apply_past_phrase("🔴", counts["remove"]),
    ]
    parts = [part for part in parts if part]
    if not parts:
        return None
    return ", ".join(parts)
