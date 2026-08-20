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

_OVERRIDE_DETAIL = (
    "The following provider development overrides are in effect:\n  - mongodbatlas in /Users/example/dev/mongodbatlas"
)


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


def _provider_override_diag(*, filename: str = ".terraformrc") -> DiagnosticBody:
    return DiagnosticBody(
        severity="warning",
        summary="Warning: Provider development overrides are in effect",
        detail=_OVERRIDE_DETAIL,
        source_range=DiagnosticRange(
            filename=filename,
            start=DiagnosticPosition(line=1, column=1, byte=0),
            end=DiagnosticPosition(line=1, column=2, byte=1),
        ),
    )


def _capture_emit(
    diags: list[DiagnosticBody],
    *,
    new_emitter_per_diag: bool = False,
) -> list[object]:
    captured: list[object] = []

    class _Console:
        @staticmethod
        def print_to_live(*objects: object) -> None:
            captured.extend(objects)

    import tfdo._internal.output.diagnostic_emitter as emitter_mod

    original = emitter_mod.ask_console
    emitter_mod.ask_console = _Console()  # type: ignore[assignment]
    try:
        if new_emitter_per_diag:
            for diag in diags:
                DiagnosticEmitter().emit(diag)
            return captured
        emitter = DiagnosticEmitter()
        for diag in diags:
            emitter.emit(diag)
        return captured
    finally:
        emitter_mod.ask_console = original


def _plain_output(captured: list[object]) -> str:
    console = create_capture_console()
    console.begin_capture()
    for item in captured:
        console.print(item)
    return console.end_capture()


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
    captured = _capture_emit(
        [
            DiagnosticBody(severity="error", summary="first failure"),
            DiagnosticBody(severity="error", summary="second failure"),
        ]
    )
    file_regression.check(_plain_output(captured), basename="multi_error_spacing", extension=".txt")


def test_provider_override_compact_and_dedup() -> None:
    override = _provider_override_diag()
    captured = _capture_emit([override, override], new_emitter_per_diag=True)
    text = _plain_output(captured)
    assert "Warning: Provider development overrides are in effect" in text
    assert "×2" in text
    assert "mongodbatlas in /Users/example" not in text
    assert ".terraformrc" not in text


def test_same_warning_different_files_not_deduped() -> None:
    captured = _capture_emit(
        [
            _provider_override_diag(filename="a.tf"),
            _provider_override_diag(filename="b.tf"),
        ]
    )
    text = _plain_output(captured)
    assert "×2" not in text
    assert text.count("Warning:") == 2


def test_duplicate_error_renders_repeat_warning() -> None:
    diag = DiagnosticBody(
        severity="error",
        summary="Error: something failed",
        detail="extra context",
    )
    captured = _capture_emit([diag, diag])
    text = _plain_output(captured)
    assert "Error:" in text
    assert "×2" in text
    assert "extra context" in text
    assert text.count("extra context") == 1


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
        assert "×2" in _plain_output(captured)
    finally:
        emitter_mod.ask_console = original
