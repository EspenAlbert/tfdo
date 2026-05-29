from __future__ import annotations

from ask_shell._internal.events import ShellRunEventT, ShellRunStdOutput

from tfdo._internal.output.apply_state import ApplyProgressState
from tfdo._internal.output.diagnostic_emitter import DiagnosticEmitter


class ApplyStreamHandler:
    def __init__(self, state: ApplyProgressState) -> None:
        self._state = state
        self._emitter = DiagnosticEmitter()
        self._carry = ""

    @property
    def state(self) -> ApplyProgressState:
        return self._state

    @property
    def emitter(self) -> DiagnosticEmitter:
        return self._emitter

    def feed_line(self, chunk: str) -> None:
        self._carry += chunk
        while "\n" in self._carry:
            line, self._carry = self._carry.split("\n", 1)
            stripped = line.strip()
            if stripped:
                self._state.feed_line(stripped + "\n")
                self._emit_drained()

    def flush(self) -> None:
        if self._carry.strip():
            self._state.feed_line(self._carry.strip() + "\n")
        self._carry = ""
        self._state.flush()
        self._emit_drained()

    def _emit_drained(self) -> None:
        for emission in self._state.drain_diagnostic_emissions():
            self._emitter.emit(emission.diagnostic, resource_addr=emission.resource_addr)


def apply_stream_callback(handler: ApplyStreamHandler):
    def callback(message: ShellRunEventT) -> bool:
        match message:
            case ShellRunStdOutput(is_stdout=True, content=content):
                handler.feed_line(content)
        return False

    return callback
