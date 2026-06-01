from __future__ import annotations

import time
from dataclasses import dataclass, field

from tfdo._internal.run.run_dir_summary import RunDirSummary


@dataclass
class OrchestrationProgressState:
    command: str
    total_dirs: int
    total_waves: int
    current_wave_index: int = 0
    dirs_completed: int = 0
    wave_dirs_total: int = 0
    wave_dirs_done: int = 0
    started_at: float = 0.0
    wave_started_at: float = 0.0
    completed_rows: list[RunDirSummary] = field(default_factory=list)

    @property
    def wave_fraction(self) -> float:
        if self.wave_dirs_total <= 0:
            return 0.0
        return self.wave_dirs_done / self.wave_dirs_total

    @property
    def global_fraction(self) -> float:
        if self.total_dirs <= 0:
            return 0.0
        return self.dirs_completed / self.total_dirs


def begin_wave(state: OrchestrationProgressState, *, wave_index: int, wave_dirs: int) -> None:
    state.current_wave_index = wave_index
    state.wave_dirs_total = wave_dirs
    state.wave_dirs_done = 0
    state.wave_started_at = time.monotonic()


def record_dir_complete(state: OrchestrationProgressState, summary: RunDirSummary) -> None:
    state.completed_rows.append(summary)
    state.dirs_completed += 1
    state.wave_dirs_done += 1
