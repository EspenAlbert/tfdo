from __future__ import annotations

from rich.text import Text

from tfdo._internal.output.diagnostic_renderer import render_diagnostic
from tfdo._internal.output.stream_models import (
    DiagnosticBody,
    DiagnosticPosition,
    DiagnosticRange,
    DiagnosticSnippet,
)


def test_warning_without_snippet_styles_label_and_detail() -> None:
    diag = DiagnosticBody(
        severity="warning",
        summary="Warning getting credentials for provider",
        detail="Service Account will be used although API Key is also set",
    )
    lines = render_diagnostic(diag)
    assert isinstance(lines[0], Text)
    assert "Warning:" in lines[0].plain
    assert "getting credentials for provider" in lines[0].plain
    assert any("Service Account will be used" in (line if isinstance(line, str) else line.plain) for line in lines)


def test_error_with_snippet_and_range() -> None:
    diag = DiagnosticBody(
        severity="error",
        summary="Invalid instance type",
        detail='"t3.micr" is not a valid instance type.',
        source_range=DiagnosticRange(
            filename="main.tf",
            start=DiagnosticPosition(line=12, column=5),
            end=DiagnosticPosition(line=12, column=20),
        ),
        snippet=DiagnosticSnippet(
            context='resource "aws_instance" "web"',
            code='  instance_type = "t3.micr"',
            start_line=12,
            highlight_start_offset=19,
            highlight_end_offset=27,
        ),
    )
    lines = render_diagnostic(diag)
    rendered = "\n".join(line.plain if isinstance(line, Text) else line for line in lines)
    assert "Error:" in rendered
    assert "main.tf:12" in rendered
    assert 'resource "aws_instance" "web"' in rendered
    assert "instance_type" in rendered
    assert "^^^^" in rendered
