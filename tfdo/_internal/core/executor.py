import logging
import shutil
from pathlib import Path

from ask_shell.shell import AbortRetryError, ShellError, ShellRun, run_and_wait

from tfdo._internal.models import InitInput, InitResult

logger = logging.getLogger(__name__)

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


def _init_should_retry(run: ShellRun) -> bool:
    """Raises AbortRetryError for non-transient errors (d08-02)."""
    stderr = run.stderr
    is_transient = _is_transient(stderr)
    is_checksum = _is_checksum_error(stderr)
    if is_checksum:
        _clean_terraform_cache(run.config.cwd)
    if is_transient or is_checksum:
        return True
    raise AbortRetryError(f"permanent error: {stderr[:200]}")


def _build_init_command(binary: str, extra_args: list[str]) -> str:
    return " ".join([binary, "init", *extra_args])


def init(input_model: InitInput) -> InitResult:
    settings = input_model.settings
    cmd = _build_init_command(settings.binary, input_model.extra_args)
    try:
        run = run_and_wait(
            cmd,
            attempts=4,
            should_retry=_init_should_retry,
            cwd=settings.work_dir,
            allow_non_zero_exit=True,
            skip_binary_check=True,
            retry_initial_wait=5,
            retry_max_wait=60,
            retry_jitter=5,
        )
        return InitResult(
            exit_code=run.exit_code or 0,
            attempts_used=run.current_attempt,
        )
    except ShellError as e:
        return InitResult(exit_code=e.exit_code or 1, attempts_used=e.run.current_attempt)
    except AbortRetryError:
        return InitResult(exit_code=1, attempts_used=1)
