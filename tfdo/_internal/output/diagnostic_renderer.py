from __future__ import annotations

from rich.text import Text

from tfdo._internal.output.stream_models import DiagnosticBody, DiagnosticSnippet

_DIAGNOSTIC_INDENT = "  "
_DETAIL_INDENT = "    "
_CODE_INDENT = "     "


def render_diagnostic(diag: DiagnosticBody) -> list[Text | str]:
    lines: list[Text | str] = []
    severity = (diag.severity or "error").lower()
    lines.append(_severity_heading(severity, _summary_after_label(diag.summary, severity)))

    if diag.source_range is not None:
        lines.append(_DETAIL_INDENT + _range_line(diag.source_range.filename, diag.source_range.start.line))

    if diag.snippet and diag.snippet.context:
        lines.append(_DETAIL_INDENT + diag.snippet.context)

    if diag.snippet:
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


def _range_line(filename: str, line: int) -> str:
    return f"{filename}:{line}"


def _snippet_lines(snippet: DiagnosticSnippet, severity: str) -> list[Text | str]:
    caret_style = "yellow" if severity == "warning" else "red"
    lines: list[Text | str] = []
    code_lines = snippet.code.splitlines()
    line_start = 0
    highlight_line = 0
    for offset, code in enumerate(code_lines):
        line_end = line_start + len(code)
        if snippet.highlight_start_offset < line_end or offset == len(code_lines) - 1:
            highlight_line = offset
        line_start = line_end + 1

    line_start = 0
    for offset, code in enumerate(code_lines):
        line_no = snippet.start_line + offset
        lines.append(f"{_CODE_INDENT}{line_no:4d} | {code}")
        if offset == highlight_line:
            local_start = snippet.highlight_start_offset - line_start
            local_end = snippet.highlight_end_offset - line_start
            caret = _caret_line(code, local_start, local_end)
            if caret:
                lines.append(Text(f"{_CODE_INDENT}     | {caret}", style=caret_style))
        line_start += len(code) + 1
    return lines


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
            if line.startswith(" ") or line.startswith("\t"):
                lines.append(_DETAIL_INDENT + line)
            else:
                lines.append(_DETAIL_INDENT + line)
    return lines
