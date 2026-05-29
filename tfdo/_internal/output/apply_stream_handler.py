from __future__ import annotations

import time

from ask_shell import console as ask_console
from ask_shell._internal.events import ShellRunEventT, ShellRunStdOutput
from ask_shell.console import RemoveLivePart
from rich.console import Console, ConsoleOptions, RenderResult

from tfdo._internal.output.apply_display import ResolvedApplyDisplay
from tfdo._internal.output.apply_renderer import (
    max_addr_width,
    render_completion_line,
    render_final_summary,
    render_live_section,
)
from tfdo._internal.output.apply_state import ApplyPhase, ApplyProgressState
from tfdo._internal.output.diagnostic_emitter import DiagnosticEmitter


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
            ask_console.print_to_live(f"{addr}: {text}", style="dim")
        addr_width = max_addr_width(self._state)
        for emission in self._state.drain_completion_emissions():
            ask_console.print_to_live(render_completion_line(emission, addr_width=addr_width))
        for emission in self._state.drain_diagnostic_emissions():
            self._emitter.emit(emission.diagnostic, resource_addr=emission.resource_addr)

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
        for line in render_final_summary(self._state, total_elapsed_s=total_elapsed, display=self._display):
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
