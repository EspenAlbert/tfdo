from __future__ import annotations

import time

from ask_shell import console as ask_console
from ask_shell._internal.events import ShellRunEventT, ShellRunStdOutput
from ask_shell.console import RemoveLivePart
from rich.console import Console, ConsoleOptions, RenderResult

from tfdo._internal.output.apply_display import ResolvedApplyDisplay
from tfdo._internal.output.apply_renderer import (
    max_addr_width,
    render_ci_completion_line,
    render_ci_final_summary,
    render_ci_heartbeat_line,
    render_completion_line,
    render_final_summary,
    render_live_section,
)
from tfdo._internal.output.apply_state import (
    ApplyPhase,
    ApplyProgressState,
    ApplyResourceStatus,
    CompletionEmission,
)
from tfdo._internal.output.diagnostic_emitter import DiagnosticEmitter
from tfdo._internal.output.stream_models import DiagnosticBody


class _ApplyStatusRenderable:
    def __init__(self, handler: ApplyStreamHandler) -> None:
        self._handler = handler

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        status = self._handler._live_status()
        if status:
            yield status


class ApplyStreamHandler:
    def __init__(
        self,
        state: ApplyProgressState,
        display: ResolvedApplyDisplay,
        *,
        interactive: bool,
        run_started: float | None = None,
    ) -> None:
        self._state = state
        self._display = display
        self._interactive = interactive
        self._started = run_started if run_started is not None else time.monotonic()
        self._emitter = DiagnosticEmitter()
        self._carry = ""
        self._summary_emitted = False
        self._remove_panel: RemoveLivePart | None = None
        self._pending_ci_error_completions: list[CompletionEmission] = []
        self._last_heartbeat: float | None = None
        if interactive:
            self._status = _ApplyStatusRenderable(self)
            self._remove_panel = ask_console.add_renderable(self._status, order=10, name="apply-status")

    @property
    def state(self) -> ApplyProgressState:
        return self._state

    @property
    def emitter(self) -> DiagnosticEmitter:
        return self._emitter

    @property
    def diagnostics_emitted(self) -> bool:
        return self._emitter.blocks_emitted > 0

    def feed_line(self, chunk: str) -> None:
        self._carry += chunk
        while "\n" in self._carry:
            line, self._carry = self._carry.split("\n", 1)
            stripped = line.strip()
            if stripped:
                self._state.ingest_line(stripped)
                self._emit_drained()

    def flush(self) -> None:
        if self._carry.strip():
            self._state.ingest_line(self._carry.strip())
        self._carry = ""
        self._state.flush()
        self._emit_drained()
        self._flush_pending_ci_error_completions()
        self._remove_live_panel()
        self._emit_final_summary()

    def _live_status(self):
        addr_width = max_addr_width(self._state)
        return render_live_section(
            self._state,
            addr_width=addr_width,
            display=self._display,
            now=time.monotonic(),
        )

    def _emit_drained(self) -> None:
        for message in self._state.drain_pre_apply_logs():
            ask_console.print_to_live(message)
        for addr, text in self._state.drain_provision_logs():
            if self._interactive:
                ask_console.print_to_live(f"{addr}: {text}", style="dim")
            else:
                ask_console.print_to_live(f"{addr}: {text}")
        if self._interactive:
            self._emit_tty_drained()
        else:
            self._emit_ci_drained()

    def _emit_tty_drained(self) -> None:
        addr_width = max_addr_width(self._state)
        for emission in self._state.drain_completion_emissions():
            ask_console.print_to_live(render_completion_line(emission, addr_width=addr_width))
        for emission in self._state.drain_diagnostic_emissions():
            self._emitter.emit(emission.diagnostic, resource_addr=emission.resource_addr)

    def _emit_ci_drained(self) -> None:
        for emission in self._state.drain_completion_emissions():
            if emission.errored:
                self._pending_ci_error_completions.append(emission)
                continue
            ask_console.print_to_live(render_ci_completion_line(emission, display=self._display))
        for emission in self._state.drain_diagnostic_emissions():
            self._flush_ci_error_completion(emission.resource_addr, emission.diagnostic)
            self._emitter.emit(emission.diagnostic, resource_addr=emission.resource_addr)
        self._maybe_emit_ci_heartbeat()

    def _flush_ci_error_completion(self, resource_addr: str | None, diagnostic: DiagnosticBody) -> None:
        if not resource_addr:
            return
        for index, pending in enumerate(self._pending_ci_error_completions):
            if pending.addr != resource_addr:
                continue
            ask_console.print_to_live(render_ci_completion_line(pending, display=self._display, diagnostic=diagnostic))
            del self._pending_ci_error_completions[index]
            return

    def _maybe_emit_ci_heartbeat(self) -> None:
        if self._state.phase != ApplyPhase.APPLYING:
            return
        in_progress = any(
            resource.status == ApplyResourceStatus.IN_PROGRESS for resource in self._state.resources.values()
        )
        if not in_progress:
            return
        now = time.monotonic()
        if self._last_heartbeat is None:
            self._last_heartbeat = now
            return
        if now - self._last_heartbeat < self._display.heartbeat_seconds:
            return
        line = render_ci_heartbeat_line(self._state, display=self._display, now=now)
        if line:
            ask_console.print_to_live(line)
        self._last_heartbeat = now

    def _flush_pending_ci_error_completions(self) -> None:
        for pending in self._pending_ci_error_completions:
            ask_console.print_to_live(render_ci_completion_line(pending, display=self._display))
        self._pending_ci_error_completions = []

    def _remove_live_panel(self) -> None:
        if self._remove_panel is None:
            return
        self._remove_panel()
        self._remove_panel = None

    def _emit_final_summary(self) -> None:
        if self._summary_emitted:
            return
        if self._state.phase != ApplyPhase.DONE and not self._all_resources_terminal():
            return
        self._summary_emitted = True
        total_elapsed = time.monotonic() - self._started
        if self._interactive:
            lines = render_final_summary(self._state, total_elapsed_s=total_elapsed, display=self._display)
        else:
            lines = render_ci_final_summary(self._state, total_elapsed_s=total_elapsed)
        for line in lines:
            ask_console.print_to_live(line)

    def _all_resources_terminal(self) -> bool:
        if not self._state.resources:
            return False
        return all(self._state.counts_toward_completed(addr) for addr in self._state.resources)


def apply_stream_callback(handler: ApplyStreamHandler):
    def callback(message: ShellRunEventT) -> bool:
        match message:
            case ShellRunStdOutput(is_stdout=True, content=content):
                handler.feed_line(content)
        return False

    return callback
