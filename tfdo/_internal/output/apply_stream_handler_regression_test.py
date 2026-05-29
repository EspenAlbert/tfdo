from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pytest_regressions.file_regression import FileRegressionFixture

from tfdo._internal.output.apply_display import ApplyDisplayCliOverrides, ApplyDisplayOptions, resolve_apply_display
from tfdo._internal.output.apply_state import ApplyProgressState, plan_from_planned_changes
from tfdo._internal.output.apply_stream_handler import ApplyStreamHandler
from tfdo._internal.output.conftest import create_capture_console
from tfdo._internal.output.models import PlanOutput
from tfdo._internal.output.parser import parse_plan_file

_REGRESSION_DIR = Path(__file__).parent / "apply_stream_handler_regression_test"


def load_regression_ndjson(name: str) -> list[str]:
    return [line for line in (_REGRESSION_DIR / name).read_text().splitlines() if line.strip()]


def _capture_tty_replay(plan: PlanOutput, lines: list[str]) -> str:
    console = create_capture_console()
    console.begin_capture()
    display = resolve_apply_display(ApplyDisplayOptions(), None, ApplyDisplayCliOverrides())
    handler = ApplyStreamHandler(
        ApplyProgressState(plan),
        display,
        interactive=False,
        run_started=1000.0,
    )

    def _print(*objects: object, **kwargs: object) -> None:
        for obj in objects:
            console.print(obj)

    module = ApplyStreamHandler.__module__
    with (
        patch(f"{module}.ask_console.print_to_live", side_effect=_print),
        patch("tfdo._internal.output.diagnostic_emitter.ask_console.print_to_live", side_effect=_print),
        patch(f"{module}.time.monotonic", return_value=1000.0),
    ):
        for line in lines:
            handler.feed_line(line + "\n")
        handler.flush()
    return console.end_capture()


def test_all_success(file_regression: FileRegressionFixture, create_flat_plan: Path) -> None:
    plan = parse_plan_file(create_flat_plan)
    text = _capture_tty_replay(plan, load_regression_ndjson("all_success.ndjson"))
    file_regression.check(text, basename="apply_tty/all_success", extension=".txt")


def test_replace_delete_create(file_regression: FileRegressionFixture) -> None:
    lines = load_regression_ndjson("replace_delete_create.ndjson")
    plan = plan_from_planned_changes(lines)
    text = _capture_tty_replay(plan, lines)
    file_regression.check(text, basename="apply_tty/replace_delete_create", extension=".txt")


def test_partial_failure_no_summary(file_regression: FileRegressionFixture) -> None:
    lines = load_regression_ndjson("partial_failure_no_summary.ndjson")
    plan = plan_from_planned_changes(lines)
    text = _capture_tty_replay(plan, lines)
    file_regression.check(text, basename="apply_tty/partial_failure_no_summary", extension=".txt")


def test_destroy_success(file_regression: FileRegressionFixture) -> None:
    lines = load_regression_ndjson("destroy_success.ndjson")
    plan = plan_from_planned_changes(lines)
    text = _capture_tty_replay(plan, lines)
    file_regression.check(text, basename="apply_tty/destroy_success", extension=".txt")
