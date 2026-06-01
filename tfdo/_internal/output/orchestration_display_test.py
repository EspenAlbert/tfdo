from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tfdo._internal.config.enums import LifecycleCommand
from tfdo._internal.output.orchestration_display import OrchestrationDisplay
from tfdo._internal.run import orchestration as orchestration_module
from tfdo._internal.run.run_dir_summary import ResourceActionCounts, RunDirSummary, build_run_dir_summary
from tfdo._internal.settings import TfDoSettings


def _plan_summary(run_dir: str = "envs/dev/app", *, duration_s: float = 2.0) -> RunDirSummary:
    return build_run_dir_summary(
        run_dir=run_dir,
        command=LifecycleCommand.PLAN,
        exit_code=0,
        skipped=False,
        duration_s=duration_s,
        resource_counts=ResourceActionCounts(add=1),
    )


def test_non_interactive_emits_ci_lines(caplog: pytest.LogCaptureFixture) -> None:
    display = OrchestrationDisplay(
        command=LifecycleCommand.PLAN,
        total_dirs=2,
        total_waves=1,
        interactive=False,
        started_at=0.0,
    )
    with patch("time.monotonic", return_value=10.0):
        display.on_wave_start(1, 2)
        display.on_dir_complete(_plan_summary())
        display.on_wave_complete(ok=1, fail=0)
        display.on_run_complete()

    messages = [r.message for r in caplog.records]
    assert any(m.startswith("orchestration: wave 1/1 started") for m in messages)
    assert any(m.startswith("plan: ✅ envs/dev/app") for m in messages)
    assert any("wave 1/1 complete" in m for m in messages)
    assert any(m.startswith("orchestration: complete") for m in messages)


def test_interactive_prints_completion_and_final() -> None:
    display = OrchestrationDisplay(
        command=LifecycleCommand.PLAN,
        total_dirs=2,
        total_waves=1,
        interactive=True,
        started_at=0.0,
    )
    console_module = __import__("ask_shell.console", fromlist=["print_to_live"])
    printed: list[object] = []

    with (
        patch("time.monotonic", return_value=5.0),
        patch.object(
            console_module,
            console_module.print_to_live.__name__,
            side_effect=lambda *args, **kwargs: printed.append(args[0]),
        ),
    ):
        display.on_dir_complete(_plan_summary())
        display.on_run_complete()

    assert any("envs/dev/app" in str(line) for line in printed)
    assert any(str(line).startswith("Run complete:") for line in printed)


def test_create_display_requires_two_dirs() -> None:
    settings = TfDoSettings(work_dir=Path("/tmp"))
    inp = orchestration_module.RunOrchestrationInput(settings=settings, command=LifecycleCommand.PLAN)
    one = orchestration_module.ExecutionPlan(waves=[orchestration_module.ExecutionWave(wave_index=0, run_dirs=["a"])])
    two = orchestration_module.ExecutionPlan(
        waves=[orchestration_module.ExecutionWave(wave_index=0, run_dirs=["a", "b"])]
    )
    assert orchestration_module._create_orchestration_display(inp, one) is None
    assert orchestration_module._create_orchestration_display(inp, two) is not None
