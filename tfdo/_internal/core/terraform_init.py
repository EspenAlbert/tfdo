from __future__ import annotations

import logging
import shutil
from pathlib import Path

from ask_shell.shell import AbortRetryError, ShellRun, run_and_wait

from tfdo._internal.core import binary
from tfdo._internal.models import InitInput, InitResult

logger = logging.getLogger(__name__)

_INIT_FAILURE_STDERR_MAX = 4000

TRANSIENT_PATTERNS: list[str] = [
    "timeout",
    "TLS handshake timeout",
    "connection reset by peer",
    "no such host",
    "i/o timeout",
    "unexpected EOF",
    "503 Service Unavailable",
    "429 Too Many Requests",
    "registry unreachable",
]

CHECKSUM_PATTERNS: list[str] = [
    "checksum",
    "does not match any of the checksums",
    "locked provider",
    "checksum list has changed",
]


def _truncate_init_stderr(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    if len(stripped) <= _INIT_FAILURE_STDERR_MAX:
        return stripped
    return f"{stripped[:_INIT_FAILURE_STDERR_MAX]}... (truncated, {len(stripped)} chars total)"


def _is_transient(stderr: str) -> bool:
    lower = stderr.lower()
    return any(p.lower() in lower for p in TRANSIENT_PATTERNS)


def _is_checksum_error(stderr: str) -> bool:
    lower = stderr.lower()
    return any(p.lower() in lower for p in CHECKSUM_PATTERNS)


def _clean_terraform_cache(cwd: Path) -> bool:
    cleaned = False
    for subdir in ("providers", "modules"):
        target = cwd / ".terraform" / subdir
        if target.is_dir():
            shutil.rmtree(target)
            logger.info(f"cleaned {target}")
            cleaned = True
    return cleaned


def terraform_init_should_retry(run: ShellRun) -> bool:
    stderr = run.stderr
    is_transient = _is_transient(stderr)
    is_checksum = _is_checksum_error(stderr)
    if is_checksum:
        _clean_terraform_cache(run.config.cwd)
    if is_transient or is_checksum:
        return True
    raise AbortRetryError(f"permanent error: {stderr[:200]}")


def _build_init_command(bin_name: str, backend_args: list[str], extra_args: list[str]) -> str:
    return " ".join([bin_name, "init", *backend_args, *extra_args])


def init(input_model: InitInput) -> InitResult:
    settings = input_model.settings
    cmd = _build_init_command(binary.resolve_binary(settings), input_model.backend_args, input_model.extra_args)
    run = run_and_wait(
        cmd,
        attempts=4,
        should_retry=terraform_init_should_retry,
        cwd=settings.work_dir,
        env=input_model.env,
        allow_non_zero_exit=True,
        ansi_content=True,
        skip_binary_check=True,
        retry_initial_wait=5,
        retry_max_wait=60,
        retry_jitter=5,
    )
    exit_code = run.exit_code or 0
    stderr_detail = _truncate_init_stderr(run.stderr) if exit_code != 0 else ""
    return InitResult(
        exit_code=exit_code,
        attempts_used=run.current_attempt,
        stdout=run.stdout,
        stderr=stderr_detail or None,
    )
