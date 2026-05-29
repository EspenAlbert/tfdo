from __future__ import annotations

from ask_shell import console as ask_console

from tfdo._internal.output.diagnostic_renderer import render_diagnostic
from tfdo._internal.output.stream_models import DiagnosticBody


class DiagnosticEmitter:
    def __init__(self) -> None:
        self.blocks_emitted = 0

    def emit(self, diag: DiagnosticBody, *, resource_addr: str | None = None, leading_blank: bool = False) -> None:
        if self.blocks_emitted:
            ask_console.print_to_live("")
        elif leading_blank:
            ask_console.print_to_live("")
        self.blocks_emitted += 1
        for line in render_diagnostic(diag, resource_addr=resource_addr):
            ask_console.print_to_live(line)
