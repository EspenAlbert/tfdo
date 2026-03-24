import logging
import shutil
from pathlib import Path

from ask_shell.shell import AbortRetryError, ShellError, ShellRun, run_and_wait

from tfdo._internal.core import binary
from tfdo._internal.models import (
    ApplyInput,
    ApplyResult,
    DestroyInput,
    DestroyResult,
    InitInput,
    InitMode,
    InitResult,
    LifecycleInput,
    LifecycleResult,
    PlanInput,
    PlanResult,
)
from tfdo._internal.settings import TfDoSettings

logger = logging.getLogger(__name__)

_INIT_FAILURE_STDERR_MAX = 4000


def _truncate_init_stderr(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    if len(stripped) <= _INIT_FAILURE_STDERR_MAX:
        return stripped
    return f"{stripped[:_INIT_FAILURE_STDERR_MAX]}... (truncated, {len(stripped)} chars total)"


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


def terraform_init_should_retry(run: ShellRun) -> bool:
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
    cmd = _build_init_command(binary.resolve_binary(settings), input_model.extra_args)
    run = run_and_wait(
        cmd,
        attempts=4,
        should_retry=terraform_init_should_retry,
        cwd=settings.work_dir,
        env=input_model.env,
        allow_non_zero_exit=True,
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
        stderr=stderr_detail or None,
    )


INIT_NEEDED_PATTERNS: list[str] = [
    "terraform init",
    "provider not installed",
    "Missing required provider",
    "Backend initialization required",
    "Module not installed",
]


def _needs_init(stderr: str) -> bool:
    lower = stderr.lower()
    return any(p.lower() in lower for p in INIT_NEEDED_PATTERNS)


def _build_lifecycle_command(binary: str, subcommand: str, var_file: Path | None, extra_flags: list[str]) -> str:
    parts = [binary, subcommand]
    if var_file:
        parts.append(f"-var-file={var_file}")
    parts.extend(extra_flags)
    return " ".join(parts)


def _run_command[T: LifecycleResult](settings: TfDoSettings, cmd: str, result_cls: type[T]) -> tuple[T, str]:
    try:
        run = run_and_wait(
            cmd,
            cwd=settings.work_dir,
            allow_non_zero_exit=True,
            skip_binary_check=True,
            user_input=settings.is_interactive,
        )
        return result_cls(exit_code=run.exit_code or 0), run.stderr
    except ShellError as e:
        return result_cls(exit_code=e.exit_code or 1), e.stderr


def _run_lifecycle[T: LifecycleResult](
    input_model: LifecycleInput, subcommand: str, extra_flags: list[str], result_cls: type[T]
) -> T:
    settings = input_model.settings
    mode = input_model.init_mode

    if mode == InitMode.ALWAYS:
        init_result = init(InitInput(settings=settings))
        if init_result.exit_code != 0:
            return result_cls(exit_code=init_result.exit_code)

    cmd = _build_lifecycle_command(binary.resolve_binary(settings), subcommand, input_model.var_file, extra_flags)
    result, stderr = _run_command(settings, cmd, result_cls)

    if result.exit_code != 0 and mode == InitMode.AUTO and _needs_init(stderr):
        logger.info(f"auto-init: detected init-needed error, running terraform init before retrying {subcommand}")
        init_result = init(InitInput(settings=settings))
        if init_result.exit_code != 0:
            return result_cls(exit_code=init_result.exit_code)
        result, _ = _run_command(settings, cmd, result_cls)

    return result


def plan(input_model: PlanInput) -> PlanResult:
    extra_flags: list[str] = []
    if input_model.out:
        extra_flags.append(f"-out={input_model.out}")
    if input_model.json_output:
        extra_flags.append("-json")
    return _run_lifecycle(input_model, "plan", extra_flags, PlanResult)


def apply(input_model: ApplyInput) -> ApplyResult:
    extra_flags: list[str] = []
    if input_model.auto_approve:
        extra_flags.append("-auto-approve")
    return _run_lifecycle(input_model, "apply", extra_flags, ApplyResult)


def destroy(input_model: DestroyInput) -> DestroyResult:
    extra_flags: list[str] = []
    if input_model.auto_approve:
        extra_flags.append("-auto-approve")
    return _run_lifecycle(input_model, "destroy", extra_flags, DestroyResult)
