from __future__ import annotations

import json

from pytest_regressions.file_regression import FileRegressionFixture

from tfdo._internal.output.conftest import create_capture_console
from tfdo._internal.output.diagnostic_emitter import DiagnosticEmitter
from tfdo._internal.output.diagnostic_renderer import render_diagnostic
from tfdo._internal.output.stream_models import (
    DiagnosticBody,
    DiagnosticEvent,
    DiagnosticPosition,
    DiagnosticRange,
    DiagnosticSnippet,
)
from tfdo._internal.output.testdata_paths import apply_progress_fixture


def _render_plain(diag: DiagnosticBody, *, resource_addr: str | None = None) -> str:
    console = create_capture_console()
    console.begin_capture()
    for line in render_diagnostic(diag, resource_addr=resource_addr):
        console.print(line)
    return console.end_capture()


def _diag_from_fixture(name: str, line_no: int) -> DiagnosticBody:
    line = apply_progress_fixture(name).read_text().splitlines()[line_no - 1]
    event = DiagnosticEvent.model_validate(json.loads(line))
    assert event.diagnostic is not None
    return event.diagnostic


def test_provision_errored(file_regression: FileRegressionFixture) -> None:
    diag = _diag_from_fixture("provision_errored.ndjson", 9)
    file_regression.check(
        _render_plain(diag, resource_addr="local_file.config"),
        basename="provision_errored",
        extension=".txt",
    )


def test_no_source_detail_only(file_regression: FileRegressionFixture) -> None:
    diag = DiagnosticBody(
        severity="error",
        summary="Error: Backend initialization required",
        detail='Run "terraform init" to prepare this working directory.',
    )
    file_regression.check(_render_plain(diag), basename="no_source", extension=".txt")


def test_warning_snippet_trim(file_regression: FileRegressionFixture) -> None:
    code = "\n".join(f"line {i}" for i in range(6))
    diag = DiagnosticBody(
        severity="warning",
        summary="Warning: Deprecated attribute",
        snippet=DiagnosticSnippet(
            code=code,
            start_line=1,
            highlight_start_offset=sum(len(x) + 1 for x in code.splitlines()[:3]),
            highlight_end_offset=sum(len(x) + 1 for x in code.splitlines()[:3]) + 4,
            context='resource "aws_instance" "web"',
        ),
        source_range=DiagnosticRange(
            filename="main.tf",
            start=DiagnosticPosition(line=8, column=1, byte=0),
            end=DiagnosticPosition(line=8, column=2, byte=1),
        ),
    )
    file_regression.check(_render_plain(diag), basename="warning_snippet_trim", extension=".txt")


def test_multi_error_spacing(file_regression: FileRegressionFixture) -> None:
    captured: list[object] = []

    class _Console:
        @staticmethod
        def print_to_live(*objects: object) -> None:
            captured.extend(objects)

    import tfdo._internal.output.diagnostic_emitter as emitter_mod

    original = emitter_mod.ask_console
    emitter_mod.ask_console = _Console()  # type: ignore[assignment]
    try:
        emitter = DiagnosticEmitter()
        diag = DiagnosticBody(severity="error", summary="first failure")
        emitter.emit(diag)
        emitter.emit(DiagnosticBody(severity="error", summary="second failure"))
        console = create_capture_console()
        console.begin_capture()
        for item in captured:
            console.print(item)
        file_regression.check(console.end_capture(), basename="multi_error_spacing", extension=".txt")
    finally:
        emitter_mod.ask_console = original


def test_emitter_counts_blocks() -> None:
    captured: list[object] = []

    class _Console:
        @staticmethod
        def print_to_live(*objects: object) -> None:
            captured.extend(objects)

    import tfdo._internal.output.diagnostic_emitter as emitter_mod

    original = emitter_mod.ask_console
    emitter_mod.ask_console = _Console()  # type: ignore[assignment]
    try:
        emitter = DiagnosticEmitter()
        diag = DiagnosticBody(severity="error", summary="one")
        emitter.emit(diag)
        emitter.emit(diag)
        assert captured.count("") == 1
        assert emitter.blocks_emitted == 2
    finally:
        emitter_mod.ask_console = original
