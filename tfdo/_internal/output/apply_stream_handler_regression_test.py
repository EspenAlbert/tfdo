from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pytest_regressions.file_regression import FileRegressionFixture

from tfdo._internal.output import apply_state
from tfdo._internal.output.apply_display import ApplyDisplayCliOverrides, ApplyDisplayOptions, resolve_apply_display
from tfdo._internal.output.apply_state import ApplyProgressState, plan_from_planned_changes
from tfdo._internal.output.apply_stream_handler import ApplyStreamHandler
from tfdo._internal.output.conftest import create_capture_console
from tfdo._internal.output.models import PlanOutput
from tfdo._internal.output.parser import parse_plan_file

_REGRESSION_DIR = Path(__file__).parent / "apply_stream_handler_regression_test"


def load_regression_ndjson(name: str) -> list[str]:
    return [line for line in (_REGRESSION_DIR / name).read_text().splitlines() if line.strip()]


def _capture_handler_replay(
    plan: PlanOutput,
    lines: list[str],
    *,
    interactive: bool,
    monotonic_values: list[float] | None = None,
) -> str:
    console = create_capture_console()
    console.begin_capture()
    display = resolve_apply_display(ApplyDisplayOptions(), None, ApplyDisplayCliOverrides())
    handler = ApplyStreamHandler(
        ApplyProgressState(plan),
        display,
        interactive=interactive,
        run_started=1000.0,
    )

    def _print(*objects: object, **kwargs: object) -> None:
        for obj in objects:
            console.print(obj)

    values = list(monotonic_values or [1000.0])
    index = 0

    def _monotonic() -> float:
        nonlocal index
        value = values[min(index, len(values) - 1)]
        index += 1
        return value

    handler_module = ApplyStreamHandler.__module__
    state_module = apply_state.__name__
    with (
        patch(f"{handler_module}.ask_console.print_to_live", side_effect=_print),
        patch("tfdo._internal.output.diagnostic_emitter.ask_console.print_to_live", side_effect=_print),
        patch(f"{handler_module}.time.monotonic", side_effect=_monotonic),
        patch(f"{state_module}.time.monotonic", side_effect=_monotonic),
    ):
        for line in lines:
            handler.feed_line(line + "\n")
        handler.flush()
    return console.end_capture()


def test_tty_all_success(file_regression: FileRegressionFixture, create_flat_plan: Path) -> None:
    plan = parse_plan_file(create_flat_plan)
    text = _capture_handler_replay(plan, load_regression_ndjson("all_success.ndjson"), interactive=True)
    file_regression.check(text, basename="apply_tty/all_success", extension=".txt")


def test_tty_replace_delete_create(file_regression: FileRegressionFixture) -> None:
    lines = load_regression_ndjson("replace_delete_create.ndjson")
    plan = plan_from_planned_changes(lines)
    text = _capture_handler_replay(plan, lines, interactive=True)
    file_regression.check(text, basename="apply_tty/replace_delete_create", extension=".txt")


def test_tty_partial_failure_no_summary(file_regression: FileRegressionFixture) -> None:
    lines = load_regression_ndjson("partial_failure_no_summary.ndjson")
    plan = plan_from_planned_changes(lines)
    text = _capture_handler_replay(plan, lines, interactive=True)
    file_regression.check(text, basename="apply_tty/partial_failure_no_summary", extension=".txt")


def test_tty_destroy_success(file_regression: FileRegressionFixture) -> None:
    lines = load_regression_ndjson("destroy_success.ndjson")
    plan = plan_from_planned_changes(lines)
    text = _capture_handler_replay(plan, lines, interactive=True)
    file_regression.check(text, basename="apply_tty/destroy_success", extension=".txt")


def test_ci_all_success(file_regression: FileRegressionFixture, create_flat_plan: Path) -> None:
    plan = parse_plan_file(create_flat_plan)
    text = _capture_handler_replay(plan, load_regression_ndjson("all_success.ndjson"), interactive=False)
    file_regression.check(text, basename="apply_ci/all_success", extension=".txt")


def test_ci_partial_failure_no_summary(file_regression: FileRegressionFixture) -> None:
    lines = load_regression_ndjson("partial_failure_no_summary.ndjson")
    plan = plan_from_planned_changes(lines)
    text = _capture_handler_replay(plan, lines, interactive=False)
    file_regression.check(text, basename="apply_ci/partial_failure_no_summary", extension=".txt")


def test_ci_destroy_success(file_regression: FileRegressionFixture) -> None:
    lines = load_regression_ndjson("destroy_success.ndjson")
    plan = plan_from_planned_changes(lines)
    text = _capture_handler_replay(plan, lines, interactive=False)
    file_regression.check(text, basename="apply_ci/destroy_success", extension=".txt")


def test_ci_heartbeat(file_regression: FileRegressionFixture) -> None:
    lines = load_regression_ndjson("heartbeat.ndjson")
    plan = plan_from_planned_changes(lines)
    text = _capture_handler_replay(
        plan,
        lines,
        interactive=False,
        monotonic_values=[1000.0, 1000.0, 1000.0, 1000.0, 1031.0, 1031.0],
    )
    file_regression.check(text, basename="apply_ci/heartbeat", extension=".txt")


def test_ci_slow_completion(file_regression: FileRegressionFixture) -> None:
    lines = load_regression_ndjson("slow_completion.ndjson")
    plan = plan_from_planned_changes(lines)
    text = _capture_handler_replay(plan, lines, interactive=False)
    file_regression.check(text, basename="apply_ci/slow_completion", extension=".txt")
