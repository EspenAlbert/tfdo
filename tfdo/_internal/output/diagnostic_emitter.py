from __future__ import annotations

from threading import Lock

from ask_shell import console as ask_console

from tfdo._internal.output.diagnostic_renderer import (
    provider_override_paths,
    render_compact_warning,
    render_diagnostic,
    render_repeat_warning,
    summary_after_label,
)
from tfdo._internal.output.orchestration_print import orchestration_print_lock
from tfdo._internal.output.stream_models import DiagnosticBody

COMPACT_WARNING_SUMMARIES = frozenset({"Provider development overrides are in effect"})

_seen_counts: dict[tuple[str, str, str, str, int], int] = {}
_seen_lock = Lock()


def reset_diagnostic_seen() -> None:
    _seen_counts.clear()


def diagnostic_identity(diag: DiagnosticBody) -> tuple[str, str, str, str, int]:
    severity = (diag.severity or "error").lower()
    normalized = summary_after_label(diag.summary, severity)
    if diag.source_range is not None:
        filename = diag.source_range.filename
        line = diag.source_range.start.line
    else:
        filename = ""
        line = 0
    return (severity, normalized, diag.detail or "", filename, line)


class DiagnosticEmitter:
    def __init__(self) -> None:
        self.blocks_emitted = 0
        self._text_parts: list[str] = []

    @property
    def combined_text(self) -> str:
        return "\n".join(self._text_parts)

    def emit(self, diag: DiagnosticBody, *, resource_addr: str | None = None, leading_blank: bool = False) -> None:
        identity = diagnostic_identity(diag)
        normalized = identity[1]
        with _seen_lock:
            count = _seen_counts.get(identity, 0) + 1
            _seen_counts[identity] = count
            if count == 1 and normalized in COMPACT_WARNING_SUMMARIES:
                self._text_parts.append(diag.summary)
                self._text_parts.extend(provider_override_paths(diag.detail))
            elif count == 1:
                self._text_parts.append(diag.summary)
                if diag.detail:
                    self._text_parts.append(diag.detail)
            else:
                self._text_parts.append(normalized)
            if count == 1 and normalized in COMPACT_WARNING_SUMMARIES:
                lines = render_compact_warning(normalized, detail=diag.detail)
            elif count == 1:
                lines = render_diagnostic(diag, resource_addr=resource_addr)
            else:
                lines = render_repeat_warning(count, normalized)

        lock = orchestration_print_lock()

        def _emit_lines() -> None:
            if self.blocks_emitted or leading_blank:
                ask_console.print_to_live("")
            self.blocks_emitted += 1
            for line in lines:
                ask_console.print_to_live(line)

        if lock is None:
            _emit_lines()
            return
        with lock:
            _emit_lines()
