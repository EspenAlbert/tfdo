from __future__ import annotations

from unittest.mock import patch

from pytest_regressions.file_regression import FileRegressionFixture

from tfdo._internal.output.apply_display import ApplyDisplayCliOverrides, ApplyDisplayOptions, resolve_apply_display
from tfdo._internal.output.apply_state import ApplyProgressState, plan_from_planned_changes
from tfdo._internal.output.apply_stream_handler import ApplyStreamHandler
from tfdo._internal.output.conftest import create_capture_console
from tfdo._internal.output.models import Change, PlanOutput, ResourceChange
from tfdo._internal.output.testdata_paths import load_apply_progress_lines


def _inline_plan(addrs: list[tuple[str, list[str]]]) -> PlanOutput:
    return PlanOutput(
        format_version="1.2",
        errored=False,
        resource_changes=[
            ResourceChange(
                address=addr,
                mode="managed",
                type="t",
                name="n",
                change=Change(actions=actions),
            )
            for addr, actions in addrs
        ],
    )


def _capture_replay(plan: PlanOutput, lines: list[str]) -> str:
    console = create_capture_console()
    console.begin_capture()
    display = resolve_apply_display(ApplyDisplayOptions(), None, ApplyDisplayCliOverrides())

    def _print(*objects: object, **kwargs: object) -> None:
        for obj in objects:
            console.print(obj)

    module = ApplyStreamHandler.__module__
    handler = ApplyStreamHandler(
        ApplyProgressState(plan),
        display,
        interactive=True,
        run_started=1000.0,
    )
    with (
        patch(f"{module}.ask_console.print_to_live", side_effect=_print),
        patch("tfdo._internal.output.diagnostic_emitter.ask_console.print_to_live", side_effect=_print),
        patch(f"{module}.time.monotonic", return_value=1000.0),
    ):
        for line in lines:
            handler.feed_line(line + "\n")
        handler.flush()
    return console.end_capture()


def test_apply_validation_failed(file_regression: FileRegressionFixture) -> None:
    plan = _inline_plan(
        [
            ("random_pet.first", ["create"]),
            ("local_file.second", ["create"]),
        ]
    )
    text = _capture_replay(plan, load_apply_progress_lines("apply_validation_failed.ndjson"))
    file_regression.check(text, basename="apply_validation_failed", extension=".txt")


def test_parallel_apply_errors(file_regression: FileRegressionFixture) -> None:
    lines = load_apply_progress_lines("parallel_apply_errors.ndjson")
    plan = plan_from_planned_changes(lines)
    text = _capture_replay(plan, lines)
    file_regression.check(text, basename="parallel_apply_errors", extension=".txt")
