from __future__ import annotations

import json
import logging
import time
from enum import StrEnum

from ask_shell import console as ask_console
from ask_shell._internal.events import ShellRunStdOutput
from ask_shell._internal.models import ShellRunEventT

from tfdo._internal.output.diagnostic_renderer import render_diagnostic
from tfdo._internal.output.render_thresholds import (
    REFRESH_HEARTBEAT_INTERVAL_S,
    REFRESH_PROGRESS_THRESHOLD_S,
)
from tfdo._internal.output.stream_models import ChangeSummaryEvent, DiagnosticEvent, RefreshEvent

logger = logging.getLogger(__name__)


class _Phase(StrEnum):
    REFRESH = "refresh"
    PLANNING = "planning"
    DONE = "done"


class PlanStreamHandler:
    def __init__(self) -> None:
        self._started = time.monotonic()
        self._phase = _Phase.REFRESH
        self._in_flight: set[str] = set()
        self._done = 0
        self._saw_refresh = False
        self._progress_enabled = False
        self._last_heartbeat = self._started
        self._planning_emitted = False
        self._diagnostic_emitted = False
        self._carry = ""

    def feed_line(self, chunk: str) -> None:
        self._carry += chunk
        while "\n" in self._carry:
            line, self._carry = self._carry.split("\n", 1)
            stripped = line.strip()
            if stripped:
                self._handle_line(stripped)

    def flush(self) -> None:
        if self._carry.strip():
            self._handle_line(self._carry.strip())
        self._carry = ""

    def _handle_line(self, line: str) -> None:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            logger.debug(f"skipping non-json plan stream line: {line[:120]!r}")
            return
        msg_type = data.get("type")
        match msg_type:
            case "diagnostic":
                self._emit_diagnostic(DiagnosticEvent.model_validate(data))
            case "refresh_start":
                self._on_refresh_start(RefreshEvent.model_validate(data))
            case "refresh_complete":
                self._on_refresh_complete(RefreshEvent.model_validate(data))
            case "change_summary":
                ChangeSummaryEvent.model_validate(data)
                self._phase = _Phase.DONE
            case "planned_change" | "resource_drift" | "outputs" | "log":
                self._leave_refresh_phase()
            case _:
                pass
        self._maybe_heartbeat()

    def _emit_diagnostic(self, event: DiagnosticEvent) -> None:
        diag = event.diagnostic
        if diag is None:
            return
        if not self._diagnostic_emitted:
            self._diagnostic_emitted = True
            ask_console.print_to_live("")
        for line in render_diagnostic(diag):
            ask_console.print_to_live(line)

    def _on_refresh_start(self, event: RefreshEvent) -> None:
        self._saw_refresh = True
        if event.hook and event.hook.resource:
            self._in_flight.add(event.hook.resource.addr)
        self._maybe_enable_progress()

    def _on_refresh_complete(self, event: RefreshEvent) -> None:
        self._saw_refresh = True
        if event.hook and event.hook.resource:
            self._in_flight.discard(event.hook.resource.addr)
        self._done += 1
        self._maybe_enable_progress()
        if not self._in_flight:
            self._leave_refresh_phase()

    def _leave_refresh_phase(self) -> None:
        if self._phase != _Phase.REFRESH:
            return
        self._phase = _Phase.PLANNING
        self._emit_planning_once()

    def _emit_planning_once(self) -> None:
        if self._planning_emitted:
            return
        self._planning_emitted = True
        ask_console.print_to_live("plan: computing changes…")

    def _maybe_enable_progress(self) -> None:
        if self._progress_enabled:
            return
        if not self._saw_refresh:
            return
        if time.monotonic() - self._started < REFRESH_PROGRESS_THRESHOLD_S:
            return
        self._progress_enabled = True

    def _maybe_heartbeat(self) -> None:
        if not self._progress_enabled or self._phase != _Phase.REFRESH:
            return
        now = time.monotonic()
        if now - self._last_heartbeat < REFRESH_HEARTBEAT_INTERVAL_S:
            return
        self._last_heartbeat = now
        ask_console.print_to_live(self._refresh_line(now - self._started))

    def _refresh_line(self, elapsed_s: float) -> str:
        mins, secs = divmod(int(elapsed_s), 60)
        elapsed = f"{mins}m {secs:02d}s" if mins else f"{secs}s"
        return f"refresh: {self._done} complete, {len(self._in_flight)} in progress ({elapsed})"


def plan_stream_callback(handler: PlanStreamHandler):
    def callback(message: ShellRunEventT) -> bool:
        match message:
            case ShellRunStdOutput(is_stdout=True, content=content):
                handler.feed_line(content)
        return False

    return callback
