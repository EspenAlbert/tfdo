from __future__ import annotations

from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn
from rich.text import Text

from tfdo._internal.config.enums import LifecycleCommand
from tfdo._internal.output.apply_display import format_elapsed, format_elapsed_compact
from tfdo._internal.output.count_phrases import (
    format_apply_aggregate_phrases,
    format_compact_action_tokens,
    format_plan_aggregate_phrases,
    sum_resource_action_counts,
)
from tfdo._internal.output.orchestration_state import OrchestrationProgressState
from tfdo._internal.run.run_dir_summary import FAILURE_LABEL, ResourceActionCounts, RunDirSummary

_CHECK_OK = "✅"
_CHECK_FAIL = "❌"
_SKIPPED = "🚫"
_FINAL_COUNTS_WIDTH = 24
_TTY_PATH_WIDTH = 28


def sum_resource_counts(summaries: list[RunDirSummary]) -> ResourceActionCounts | None:
    rows = [s.resource_counts for s in summaries if not s.skipped]
    return sum_resource_action_counts(rows)


def format_output_badge(count: int | None, *, command: str) -> str:
    if command == LifecycleCommand.PLAN and count:
        return f"📤{count}"
    return ""


def format_dir_counts_segment(summary: RunDirSummary) -> str:
    if summary.skipped:
        return ""
    if summary.failure_label:
        return summary.failure_label
    counts = summary.resource_counts
    if counts is None:
        if summary.exit_code == 0:
            return "no changes"
        return FAILURE_LABEL
    compact = format_compact_action_tokens(counts, include_replace=summary.command == LifecycleCommand.PLAN)
    return compact or "no changes"


def render_wave_started(state: OrchestrationProgressState) -> str:
    return f"orchestration: wave {state.current_wave_index}/{state.total_waves} started ({state.wave_dirs_total} dirs)"


def render_wave_complete(state: OrchestrationProgressState, *, ok: int, fail: int) -> str:
    return f"orchestration: wave {state.current_wave_index}/{state.total_waves} complete ({ok} ✅, {fail} ❌)"


def _status_marker(summary: RunDirSummary) -> str:
    if summary.skipped:
        return _SKIPPED
    return _CHECK_FAIL if summary.exit_code != 0 else _CHECK_OK


def _ci_prefix(command: str) -> str:
    return f"{command}:"


def render_dir_completion_ci(summary: RunDirSummary) -> str:
    marker = _status_marker(summary)
    counts = format_dir_counts_segment(summary)
    badge = format_output_badge(summary.output_change_count, command=summary.command)
    duration = "-" if summary.skipped else format_elapsed_compact(summary.duration_s)
    parts = [_ci_prefix(summary.command), marker, summary.run_dir]
    if counts:
        parts.append(counts)
    if badge:
        parts.append(badge)
    parts.append(duration)
    return " ".join(parts)


def render_orchestration_complete_ci(state: OrchestrationProgressState, *, total_elapsed_s: float) -> str:
    elapsed = format_elapsed(total_elapsed_s)
    return f"orchestration: complete {state.total_dirs} dirs, {state.total_waves} waves, {elapsed}"


def render_aggregate_line(command: str, totals: ResourceActionCounts | None) -> str | None:
    if totals is None:
        return None
    match command:
        case LifecycleCommand.PLAN:
            phrases = format_plan_aggregate_phrases(totals)
            if not phrases:
                return None
            return f"📋 Plan: {', '.join(phrases)}"
        case LifecycleCommand.APPLY:
            phrases = format_apply_aggregate_phrases(totals)
            if not phrases:
                return None
            return f"Apply: {', '.join(phrases)}"
        case LifecycleCommand.DESTROY:
            phrases = format_apply_aggregate_phrases(totals)
            if not phrases:
                return None
            return f"Destroy: {', '.join(phrases)}"
        case _:
            return None


def render_run_complete_header(state: OrchestrationProgressState, *, total_elapsed_s: float) -> str:
    elapsed = format_elapsed(total_elapsed_s)
    dir_word = "directory" if state.total_dirs == 1 else "directories"
    wave_word = "wave" if state.total_waves == 1 else "waves"
    return f"Run complete: {state.total_dirs} {dir_word}, {state.total_waves} {wave_word}  total {elapsed}"


def _counts_with_badge(summary: RunDirSummary) -> str:
    segment = format_dir_counts_segment(summary)
    badge = format_output_badge(summary.output_change_count, command=summary.command)
    if badge:
        return f"{segment} {badge}".strip() if segment else badge
    return segment


def render_final_dir_row_plain(summary: RunDirSummary) -> str:
    marker = _status_marker(summary)
    if summary.skipped:
        return f"{marker}  {_FINAL_COUNTS_WIDTH * ' '} {summary.run_dir}  -"
    counts = _counts_with_badge(summary)
    duration = format_elapsed_compact(summary.duration_s)
    return f"{marker} {counts:<{_FINAL_COUNTS_WIDTH}} {summary.run_dir}  {duration}"


def render_final_dir_row_styled(summary: RunDirSummary) -> Text:
    line = render_final_dir_row_plain(summary)
    if summary.skipped:
        return Text(line, style="dim")
    if summary.exit_code != 0:
        return Text(line, style="red")
    return Text(line)


def render_completed_dir_tty(summary: RunDirSummary) -> str:
    marker = _status_marker(summary)
    counts = _counts_with_badge(summary)
    duration = "-" if summary.skipped else format_elapsed_compact(summary.duration_s)
    path = summary.run_dir.ljust(_TTY_PATH_WIDTH)
    middle = f"{summary.command}  {counts}".rstrip()
    return f"{marker} {path}  {middle}  {duration}".rstrip()


def render_final_summary(
    state: OrchestrationProgressState,
    *,
    total_elapsed_s: float,
    interactive: bool = False,
) -> list[str | Text]:
    lines: list[str | Text] = [render_run_complete_header(state, total_elapsed_s=total_elapsed_s)]
    totals = sum_resource_counts(state.completed_rows)
    aggregate = render_aggregate_line(state.command, totals)
    if aggregate:
        lines.append(aggregate)
    for summary in state.completed_rows:
        lines.append(render_final_dir_row_styled(summary) if interactive else render_final_dir_row_plain(summary))
    return lines


def render_non_tty_footer(state: OrchestrationProgressState, *, total_elapsed_s: float) -> list[str]:
    lines = [render_orchestration_complete_ci(state, total_elapsed_s=total_elapsed_s)]
    if state.command in {LifecycleCommand.APPLY, LifecycleCommand.DESTROY}:
        totals = sum_resource_counts(state.completed_rows)
        aggregate = render_aggregate_line(state.command, totals)
        if aggregate:
            lines.append(aggregate)
    return lines


def render_orchestration_live_header(state: OrchestrationProgressState) -> str:
    return (
        f"Orchestration: wave {state.current_wave_index}/{state.total_waves}  "
        f"dirs {state.dirs_completed}/{state.total_dirs}"
    )


def build_wave_progress(state: OrchestrationProgressState, *, now: float) -> Progress:
    elapsed = format_elapsed(max(0.0, now - state.wave_started_at))
    progress = Progress(
        TextColumn("  [progress.description]{task.description}"),
        TaskProgressColumn(),
        BarColumn(),
        TextColumn(elapsed),
        expand=True,
        transient=True,
    )
    total = max(state.wave_dirs_total, 1)
    progress.add_task(
        f"wave-{state.current_wave_index}",
        total=total,
        completed=min(state.wave_dirs_done, total),
    )
    return progress
