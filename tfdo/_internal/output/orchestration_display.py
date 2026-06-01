from __future__ import annotations

import logging
import time
from threading import Lock

from ask_shell import console as ask_console

from tfdo._internal.output import orchestration_renderer as renderer
from tfdo._internal.output.orchestration_state import OrchestrationProgressState, begin_wave, record_dir_complete
from tfdo._internal.run.run_dir_summary import RunDirSummary

logger = logging.getLogger(__name__)


class OrchestrationDisplay:
    def __init__(
        self,
        *,
        command: str,
        total_dirs: int,
        total_waves: int,
        interactive: bool,
        started_at: float | None = None,
    ) -> None:
        started = started_at if started_at is not None else time.monotonic()
        self._interactive = interactive
        self._started_at = started
        self._lock = Lock()
        self.state = OrchestrationProgressState(
            command=command,
            total_dirs=total_dirs,
            total_waves=total_waves,
            started_at=started,
        )

    @staticmethod
    def log_dry_run_line(wave_index: int, run_dir: str, command: str) -> None:
        logger.info(f"[dry-run] wave {wave_index}: {run_dir} -> {command}")

    def on_wave_start(self, wave_index: int, wave_dirs: int) -> None:
        with self._lock:
            begin_wave(self.state, wave_index=wave_index, wave_dirs=wave_dirs)
            if not self._interactive:
                logger.info(renderer.render_wave_started(self.state))

    def on_dir_complete(self, summary: RunDirSummary) -> None:
        with self._lock:
            record_dir_complete(self.state, summary)
            if self._interactive:
                ask_console.print_to_live(renderer.render_completed_dir_tty(summary))
            else:
                logger.info(renderer.render_dir_completion_ci(summary))

    def on_wave_complete(self, *, ok: int, fail: int) -> None:
        if self._interactive:
            return
        with self._lock:
            logger.info(renderer.render_wave_complete(self.state, ok=ok, fail=fail))

    def on_run_complete(self) -> None:
        elapsed = time.monotonic() - self._started_at
        with self._lock:
            if self._interactive:
                for line in renderer.render_final_summary(self.state, total_elapsed_s=elapsed, interactive=True):
                    ask_console.print_to_live(line)
            else:
                for line in renderer.render_non_tty_footer(self.state, total_elapsed_s=elapsed):
                    logger.info(line)
