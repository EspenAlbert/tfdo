from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import StringIO
from threading import Lock
from unittest.mock import patch

from pytest_regressions.file_regression import FileRegressionFixture
from rich.console import Console

from tfdo._internal.config.enums import LifecycleCommand
from tfdo._internal.output.orchestration_live import OrchestrationStatusRenderable
from tfdo._internal.output.orchestration_renderer import render_orchestration_live_header
from tfdo._internal.output.orchestration_state import OrchestrationProgressState


def _mid_run_state() -> OrchestrationProgressState:
    return OrchestrationProgressState(
        command=LifecycleCommand.PLAN,
        total_dirs=10,
        total_waves=3,
        current_wave_index=2,
        dirs_completed=6,
        wave_dirs_total=5,
        wave_dirs_done=3,
        wave_started_at=1000.0,
    )


def test_live_header() -> None:
    assert render_orchestration_live_header(_mid_run_state()) == "Orchestration: wave 2/3  dirs 6/10"


def _stabilize_progress_line(line: str) -> str:
    line = re.sub(r"[━─]+", "<bar>", line)
    return re.sub(r" {2,}", " ", line).strip()


def _stabilize_orchestration_live_snapshot(text: str) -> str:
    lines = text.strip().splitlines()
    if not lines:
        return ""
    header = lines[0]
    progress = [_stabilize_progress_line(line) for line in lines[1:]]
    return "\n".join([header, *progress])


@dataclass
class _LiveHost:
    state: OrchestrationProgressState
    _lock: Lock = field(default_factory=Lock)


def test_in_progress_live_regression(file_regression: FileRegressionFixture) -> None:
    display = _LiveHost(state=_mid_run_state())
    buffer = StringIO()
    console = Console(
        width=120,
        force_terminal=True,
        color_system=None,
        file=buffer,
        legacy_windows=False,
    )
    renderable = OrchestrationStatusRenderable(display)
    with patch("time.monotonic", return_value=1012.0):
        for part in renderable.__rich_console__(console, console.options):
            console.print(part)
    snapshot = _stabilize_orchestration_live_snapshot(buffer.getvalue())
    file_regression.check(snapshot, basename="orchestration_tty/in_progress", extension=".txt")
