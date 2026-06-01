from __future__ import annotations

from pytest_regressions.file_regression import FileRegressionFixture

from tfdo._internal.config.enums import LifecycleCommand
from tfdo._internal.output.orchestration_renderer import (
    render_aggregate_line,
    render_dir_completion_ci,
    render_final_summary,
    render_non_tty_footer,
    render_wave_complete,
    render_wave_started,
    sum_resource_counts,
)
from tfdo._internal.output.orchestration_state import OrchestrationProgressState, begin_wave, record_dir_complete
from tfdo._internal.run.run_dir_summary import ResourceActionCounts, build_run_dir_summary, skipped_run_dir_summary


def _plan_rows() -> list:
    return [
        build_run_dir_summary(
            run_dir="envs/staging/networking",
            command=LifecycleCommand.PLAN,
            exit_code=0,
            skipped=False,
            duration_s=4.2,
            resource_counts=ResourceActionCounts(add=3, change=1),
            output_change_count=2,
        ),
        build_run_dir_summary(
            run_dir="envs/staging/database",
            command=LifecycleCommand.PLAN,
            exit_code=0,
            skipped=False,
            duration_s=2.3,
            resource_counts=None,
            has_applyable_changes=False,
        ),
        build_run_dir_summary(
            run_dir="envs/staging/monitoring",
            command=LifecycleCommand.PLAN,
            exit_code=1,
            skipped=False,
            duration_s=1.8,
        ),
        skipped_run_dir_summary("envs/prod/monitoring", LifecycleCommand.PLAN, 0),
    ]


def _apply_rows() -> list:
    return [
        build_run_dir_summary(
            run_dir="envs/staging/networking",
            command=LifecycleCommand.APPLY,
            exit_code=0,
            skipped=False,
            duration_s=11.2,
            resource_counts=ResourceActionCounts(add=3, change=1),
        ),
        build_run_dir_summary(
            run_dir="envs/staging/compute",
            command=LifecycleCommand.APPLY,
            exit_code=1,
            skipped=False,
            duration_s=4.8,
            resource_counts=ResourceActionCounts(add=1),
        ),
        build_run_dir_summary(
            run_dir="envs/staging/database",
            command=LifecycleCommand.APPLY,
            exit_code=0,
            skipped=False,
            duration_s=2.1,
            resource_counts=None,
        ),
    ]


def _state(command: LifecycleCommand, rows: list) -> OrchestrationProgressState:
    state = OrchestrationProgressState(command=command, total_dirs=len(rows), total_waves=2)
    begin_wave(state, wave_index=1, wave_dirs=3)
    for row in rows:
        record_dir_complete(state, row)
    return state


def test_sum_and_aggregate() -> None:
    totals = sum_resource_counts(_plan_rows())
    assert totals is not None
    assert totals.add == 3
    line = render_aggregate_line(LifecycleCommand.PLAN, totals)
    assert line is not None
    assert "📋 Plan:" in line
    assert "to add" in line


def test_plan_final_summary_regression(file_regression: FileRegressionFixture) -> None:
    state = _state(LifecycleCommand.PLAN, _plan_rows())
    lines = render_final_summary(state, total_elapsed_s=48.0, interactive=False)
    file_regression.check("\n".join(str(line) for line in lines), basename="plan_final", extension=".txt")


def test_plan_ci_regression(file_regression: FileRegressionFixture) -> None:
    wave1, wave2 = _plan_rows()[:2], [_plan_rows()[2]]
    state = OrchestrationProgressState(command=LifecycleCommand.PLAN, total_dirs=3, total_waves=2)
    begin_wave(state, wave_index=1, wave_dirs=2)
    out = [
        render_wave_started(state),
        *[render_dir_completion_ci(r) for r in wave1],
        render_wave_complete(state, ok=2, fail=0),
    ]
    begin_wave(state, wave_index=2, wave_dirs=1)
    out.extend(
        [
            render_wave_started(state),
            render_dir_completion_ci(wave2[0]),
            render_wave_complete(state, ok=0, fail=1),
            *render_non_tty_footer(state, total_elapsed_s=48.0),
        ]
    )
    file_regression.check("\n".join(out), basename="plan_ci", extension=".txt")


def test_apply_final_summary_regression(file_regression: FileRegressionFixture) -> None:
    state = _state(LifecycleCommand.APPLY, _apply_rows())
    lines = render_final_summary(state, total_elapsed_s=314.0, interactive=False)
    file_regression.check("\n".join(str(line) for line in lines), basename="apply_final", extension=".txt")


def test_apply_ci_regression(file_regression: FileRegressionFixture) -> None:
    rows = _apply_rows()
    state = OrchestrationProgressState(command=LifecycleCommand.APPLY, total_dirs=3, total_waves=1)
    begin_wave(state, wave_index=1, wave_dirs=3)
    for row in rows:
        record_dir_complete(state, row)
    out = [
        render_wave_started(state),
        *[render_dir_completion_ci(r) for r in rows],
        *render_non_tty_footer(state, total_elapsed_s=314.0),
    ]
    file_regression.check("\n".join(out), basename="apply_ci", extension=".txt")


def test_destroy_ci_prefix() -> None:
    row = build_run_dir_summary(
        run_dir="envs/dev/app",
        command=LifecycleCommand.DESTROY,
        exit_code=0,
        skipped=False,
        duration_s=5.0,
        resource_counts=ResourceActionCounts(destroy=2),
    )
    assert render_dir_completion_ci(row).startswith("destroy:")
