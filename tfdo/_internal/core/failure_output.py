from __future__ import annotations

import logging

from ask_shell import console as ask_console

logger = logging.getLogger(__name__)

_FAILURE_STDERR_MAX = 4000
_FAILURE_STDERR_TAIL_LINES = 40


def is_plan_hard_failure(exit_code: int) -> bool:
    return exit_code == 1


def format_failure_stderr(stderr: str | None) -> str | None:
    if stderr is None:
        return None
    stripped = stderr.strip()
    if not stripped:
        return None
    lines = stripped.splitlines()
    tail = lines[-_FAILURE_STDERR_TAIL_LINES:]
    text = "\n".join(tail)
    if len(text) <= _FAILURE_STDERR_MAX:
        return text
    return f"... (truncated, {len(text)} chars total)\n{text[-_FAILURE_STDERR_MAX:]}"


def report_lifecycle_failure(
    *,
    command: str,
    exit_code: int,
    stderr: str | None = None,
    message: str | None = None,
    diagnostics_already_shown: bool = False,
) -> None:
    body = message
    if body is None and not diagnostics_already_shown:
        body = format_failure_stderr(stderr)
    if not body:
        logger.error(f"{command} failed with exit code {exit_code}")
        return
    heading = f"{command} failed (exit {exit_code})"
    ask_console.print_to_live(heading, style="bold red")
    ask_console.print_to_live(body)
    logger.error(f"{heading}\n{body}")
