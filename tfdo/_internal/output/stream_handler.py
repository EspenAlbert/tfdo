from __future__ import annotations

import json
import logging
import time
from enum import StrEnum

from ask_shell import console as ask_console
from ask_shell._internal.events import ShellRunEventT, ShellRunStdOutput
from ask_shell.console import RemoveLivePart
from rich.console import Console, ConsoleOptions, RenderResult
from rich.text import Text

from tfdo._internal.output.apply_live_mode import plan_status_renderable_name
from tfdo._internal.output.diagnostic_emitter import DiagnosticEmitter
from tfdo._internal.output.diagnostic_link import resolve_resource_addr
from tfdo._internal.output.stream_models import ChangeSummaryEvent, DiagnosticEvent, RefreshEvent

logger = logging.getLogger(__name__)


class _Phase(StrEnum):
    REFRESH = "refresh"
    PLANNING = "planning"
    DONE = "done"


class _PlanStatusRenderable:
    def __init__(self, handler: PlanStreamHandler) -> None:
        self._handler = handler

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        status = self._handler._status_line()
        if status:
            yield status


class PlanStreamHandler:
    def __init__(self, *, run_dir_key: str = "") -> None:
        self._started = time.monotonic()
        self._phase = _Phase.REFRESH
        self._in_flight: set[str] = set()
        self._done = 0
        self._planning_emitted = False
        self._diagnostics = DiagnosticEmitter()
        self._carry = ""
        self._status = _PlanStatusRenderable(self)
        self._remove_panel: RemoveLivePart | None = ask_console.add_renderable(
            self._status, order=10, name=plan_status_renderable_name(run_dir_key)
        )

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
        self._remove_status_panel()

    @property
    def diagnostics_emitted(self) -> bool:
        return self._diagnostics.blocks_emitted > 0

    def _handle_line(self, line: str) -> None:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            logger.debug(f"skipping non-json plan stream line: {line[:120]!r}")
            return
        msg_type = data.get("type")
        event = RefreshEvent.model_validate(data)
        match msg_type:
            case "diagnostic":
                self._emit_diagnostic(DiagnosticEvent.model_validate(data))
            case "refresh_start" | "apply_start":
                self._on_refresh_start(event)
            case "refresh_complete" | "apply_complete":
                self._on_refresh_complete(event)
            case "change_summary":
                ChangeSummaryEvent.model_validate(data)
                self._phase = _Phase.DONE
            case "planned_change" | "resource_drift" | "outputs" | "log":
                self._leave_refresh_phase()
            case _:
                pass

    def _emit_diagnostic(self, event: DiagnosticEvent) -> None:
        diag = event.diagnostic
        if diag is None:
            return
        resource_addr = resolve_resource_addr(diag)
        self._diagnostics.emit(diag, resource_addr=resource_addr, leading_blank=not self._diagnostics.blocks_emitted)

    def _on_refresh_start(self, event: RefreshEvent) -> None:
        if event.hook and event.hook.resource:
            self._in_flight.add(event.hook.resource.addr)

    def _on_refresh_complete(self, event: RefreshEvent) -> None:
        if event.hook and event.hook.resource:
            self._in_flight.discard(event.hook.resource.addr)
        self._done += 1
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

    def _status_line(self) -> Text | None:
        if self._phase == _Phase.DONE:
            return None
        if self._phase == _Phase.PLANNING:
            return Text("planning…", style="cyan")
        return self._refresh_status(time.monotonic() - self._started)

    def _refresh_status(self, elapsed_s: float) -> Text:
        mins, secs = divmod(int(elapsed_s), 60)
        elapsed = f"{mins}m {secs:02d}s" if mins else f"{secs}s"
        return Text.assemble(
            ("refresh", "cyan"),
            " · ",
            (str(self._done), "bold"),
            " done · ",
            (str(len(self._in_flight)), "bold"),
            " running · ",
            (elapsed, "dim"),
        )

    def _remove_status_panel(self) -> None:
        if self._remove_panel is None:
            return
        self._remove_panel()
        self._remove_panel = None


def plan_stream_callback(handler: PlanStreamHandler):
    def callback(message: ShellRunEventT) -> bool:
        match message:
            case ShellRunStdOutput(is_stdout=True, content=content):
                handler.feed_line(content)
        return False

    return callback
