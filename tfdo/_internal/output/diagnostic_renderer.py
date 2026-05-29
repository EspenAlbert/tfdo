from __future__ import annotations

from rich.text import Text

from tfdo._internal.output.stream_models import DiagnosticBody, DiagnosticSnippet

SNIPPET_LINES_BEFORE = 2
SNIPPET_LINES_AFTER = 1

_DIAGNOSTIC_INDENT = "  "
_DETAIL_INDENT = "    "
_CODE_INDENT = "     "


def render_diagnostic(diag: DiagnosticBody, *, resource_addr: str | None = None) -> list[Text | str]:
    lines: list[Text | str] = []
    severity = (diag.severity or "error").lower()
    lines.append(_severity_heading(severity, _summary_after_label(diag.summary, severity)))

    has_source = diag.source_range is not None or diag.snippet is not None
    if diag.source_range is not None:
        lines.append(_range_text(diag.source_range.filename, diag.source_range.start.line))
    if resource_addr:
        lines.append(_DETAIL_INDENT + resource_addr)
    if diag.snippet and has_source:
        lines.extend(_snippet_lines(diag.snippet, severity))

    if diag.detail:
        lines.extend(_detail_lines(diag.detail))

    return lines


def _summary_after_label(summary: str, severity: str) -> str:
    match severity:
        case "warning":
            for prefix in ("Warning: ", "Warning "):
                if summary.startswith(prefix):
                    return summary[len(prefix) :]
        case "error":
            for prefix in ("Error: ", "Error "):
                if summary.startswith(prefix):
                    return summary[len(prefix) :]
    return summary


def _severity_heading(severity: str, summary: str) -> Text:
    text = Text(_DIAGNOSTIC_INDENT)
    match severity:
        case "warning":
            text.append("Warning: ", style="bold yellow")
        case "error":
            text.append("Error: ", style="bold red")
        case _:
            text.append(f"{severity.title()}: ", style="bold")
    text.append(summary)
    return text


def _range_text(filename: str, line: int) -> Text:
    return Text.assemble((_DETAIL_INDENT, ""), (f"{filename}:{line}", "dim"))


def _snippet_lines(snippet: DiagnosticSnippet, severity: str) -> list[Text | str]:
    caret_style = "yellow" if severity == "warning" else "red"
    code_lines = snippet.code.splitlines()
    if not code_lines:
        return []

    highlight_line = _highlight_line_index(snippet, code_lines)
    window_start = max(0, highlight_line - SNIPPET_LINES_BEFORE)
    window_end = min(len(code_lines), highlight_line + SNIPPET_LINES_AFTER + 1)
    sliced = code_lines[window_start:window_end]

    prefix_len = sum(len(line) + 1 for line in code_lines[:window_start])
    start_offset = snippet.highlight_start_offset - prefix_len
    end_offset = snippet.highlight_end_offset - prefix_len
    start_line = snippet.start_line + window_start
    highlight_in_slice = highlight_line - window_start

    lines: list[Text | str] = []
    for offset, code in enumerate(sliced):
        line_no = start_line + offset
        lines.append(Text.assemble((_CODE_INDENT, ""), (f"{line_no:4d}", "dim"), " | ", code))
        if offset == highlight_in_slice:
            caret = _caret_line(code, start_offset, end_offset)
            if caret:
                lines.append(Text.assemble((_CODE_INDENT, ""), ("     | ", "dim"), (caret, caret_style)))
    return lines


def _highlight_line_index(snippet: DiagnosticSnippet, code_lines: list[str]) -> int:
    line_start = 0
    for offset, code in enumerate(code_lines):
        line_end = line_start + len(code)
        if snippet.highlight_start_offset < line_end:
            return offset
        line_start = line_end + 1
    return max(len(code_lines) - 1, 0)


def _caret_line(code: str, start: int, end: int) -> str:
    if start < 0 or end < start:
        return ""
    start = min(start, len(code))
    end = min(end, len(code))
    if start == end and start < len(code):
        end = start + 1
    return f"{' ' * start}{'^' * max(1, end - start)}"


def _detail_lines(detail: str) -> list[str]:
    lines: list[str] = []
    for block in detail.split("\n\n"):
        if not block:
            continue
        for line in block.splitlines():
            lines.append(_DETAIL_INDENT + line)
    return lines
