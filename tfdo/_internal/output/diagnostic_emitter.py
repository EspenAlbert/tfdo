from __future__ import annotations

from ask_shell import console as ask_console

from tfdo._internal.output.diagnostic_renderer import render_diagnostic
from tfdo._internal.output.orchestration_print import orchestration_print_lock
from tfdo._internal.output.stream_models import DiagnosticBody


class DiagnosticEmitter:
    def __init__(self) -> None:
        self.blocks_emitted = 0
        self._text_parts: list[str] = []

    @property
    def combined_text(self) -> str:
        return "\n".join(self._text_parts)

    def emit(self, diag: DiagnosticBody, *, resource_addr: str | None = None, leading_blank: bool = False) -> None:
        self._text_parts.append(diag.summary)
        if diag.detail:
            self._text_parts.append(diag.detail)
        lock = orchestration_print_lock()

        def _emit_lines() -> None:
            if self.blocks_emitted or leading_blank:
                ask_console.print_to_live("")
            self.blocks_emitted += 1
            for line in render_diagnostic(diag, resource_addr=resource_addr):
                ask_console.print_to_live(line)

        if lock is None:
            _emit_lines()
            return
        with lock:
            _emit_lines()
