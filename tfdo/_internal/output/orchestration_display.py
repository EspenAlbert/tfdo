from __future__ import annotations

import logging
import time
from threading import Lock

from ask_shell import console as ask_console
from ask_shell.console import RemoveLivePart

from tfdo._internal.config.enums import LifecycleCommand
from tfdo._internal.output import orchestration_print
from tfdo._internal.output import orchestration_renderer as renderer
from tfdo._internal.output.orchestration_live import register_orchestration_live
from tfdo._internal.output.orchestration_state import OrchestrationProgressState, begin_wave, record_dir_complete
from tfdo._internal.output.plan_display import DetailLevel
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
        detail: DetailLevel = DetailLevel.COMPACT,
        started_at: float | None = None,
    ) -> None:
        started = started_at if started_at is not None else time.monotonic()
        orchestration_print.reset_orchestration_dir_blocks()
        self._interactive = interactive
        self._detail = detail
        self._started_at = started
        self._lock = Lock()
        self._print_lock = Lock()
        self.state = OrchestrationProgressState(
            command=command,
            total_dirs=total_dirs,
            total_waves=total_waves,
            started_at=started,
        )
        self._remove_live: RemoveLivePart | None = None
        if interactive:
            self._remove_live = register_orchestration_live(self)

    @property
    def print_lock(self) -> Lock:
        return self._print_lock

    @staticmethod
    def log_dry_run_line(wave_index: int, run_dir: str, command: str) -> None:
        logger.info(f"[dry-run] wave {wave_index}: {run_dir} -> {command}")

    def on_wave_start(self, wave_index: int, wave_dirs: int) -> None:
        with self._lock:
            begin_wave(self.state, wave_index=wave_index, wave_dirs=wave_dirs)
            tty_lines: list[str] = []
            if self._interactive:
                if wave_index > 1:
                    tty_lines.append("")
                tty_lines.append(renderer.render_wave_tty_header(self.state))
            ci_line = None if self._interactive else renderer.render_wave_started(self.state)
        if tty_lines:
            with self._print_lock:
                for line in tty_lines:
                    ask_console.print_to_live(line)
        if ci_line is not None:
            logger.info(ci_line)

    def on_dir_complete(self, summary: RunDirSummary) -> None:
        with self._lock:
            record_dir_complete(self.state, summary)
            emit_live_completion_row = self._interactive and (
                summary.command != LifecycleCommand.PLAN or self._detail == DetailLevel.COMPACT
            )
            tty_line = renderer.render_completed_dir_tty(summary) if emit_live_completion_row else None
            ci_line = None if self._interactive else renderer.render_dir_completion_ci(summary)
        if tty_line is not None:
            with self._print_lock:
                ask_console.print_to_live(tty_line)
        elif ci_line is not None:
            logger.info(ci_line)

    def on_wave_complete(self, *, ok: int, fail: int) -> None:
        if self._interactive:
            return
        with self._lock:
            ci_line = renderer.render_wave_complete(self.state, ok=ok, fail=fail)
        logger.info(ci_line)

    def on_run_complete(self) -> None:
        self._remove_live_panel()
        elapsed = time.monotonic() - self._started_at
        with self._lock:
            if self._interactive:
                final_lines = list(renderer.render_final_summary(self.state, total_elapsed_s=elapsed, interactive=True))
            else:
                final_lines = list(renderer.render_non_tty_footer(self.state, total_elapsed_s=elapsed))
        if self._interactive:
            with self._print_lock:
                for line in final_lines:
                    ask_console.print_to_live(line)
        else:
            for line in final_lines:
                logger.info(line)

    def _remove_live_panel(self) -> None:
        if self._remove_live is None:
            return
        self._remove_live(print_after_removing=False)
        self._remove_live = None
