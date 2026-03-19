from __future__ import annotations

import logging
from pathlib import Path
from typing import NamedTuple

from ask_shell._internal.run_pool import run_pool
from ask_shell.shell import ShellError, run_and_wait

from tfdo._internal.core import binary
from tfdo._internal.core.executor import init
from tfdo._internal.core.tf_files import TERRAFORM_DIR, find_tf_directories
from tfdo._internal.models import CheckInput, CheckResult, DirCheckResult, InitInput, InitMode, ValidateOutput
from tfdo._internal.settings import TfDoSettings

logger = logging.getLogger(__name__)


def _build_fmt_command(resolved_binary: str, fix: bool, diff: bool) -> str:
    parts = [resolved_binary, "fmt"]
    if not fix:
        parts.append("-check")
    if diff:
        parts.append("-diff")
    parts.append(".")
    return " ".join(parts)


def _parse_fmt_files(stdout: str) -> list[str]:
    if not stdout.strip():
        return []
    return [line.strip() for line in stdout.strip().splitlines() if line.strip()]


def _build_validate_command(resolved_binary: str) -> str:
    return f"{resolved_binary} validate -json"


class _FmtResult(NamedTuple):
    files: list[str]
    stdout: str


class _DirRunResult(NamedTuple):
    fmt: _FmtResult
    validation_errors: list[str]
    skipped: bool


def _run_fmt(resolved_binary: str, cwd: Path, fix: bool, diff: bool) -> _FmtResult:
    cmd = _build_fmt_command(resolved_binary, fix, diff)
    try:
        run = run_and_wait(cmd, cwd=cwd, allow_non_zero_exit=True, skip_binary_check=True)
        files = [] if fix else _parse_fmt_files(run.stdout)
        return _FmtResult(files=files, stdout=run.stdout)
    except ShellError as e:
        files = [] if fix else _parse_fmt_files(e.run.stdout)
        return _FmtResult(files=files, stdout=e.run.stdout)


def _run_validate(resolved_binary: str, cwd: Path) -> list[str]:
    cmd = _build_validate_command(resolved_binary)
    try:
        run = run_and_wait(cmd, cwd=cwd, allow_non_zero_exit=True, skip_binary_check=True)
        output = run.parse_output(ValidateOutput)
        return output.error_summaries
    except ShellError as e:
        output = e.run.parse_output(ValidateOutput)
        return output.error_summaries
    except Exception:
        return []


def _ensure_initialized(tf_dir: Path, mode: InitMode, settings: TfDoSettings) -> bool:
    """Returns True if the directory is ready for validate, False if it should be skipped."""
    if (tf_dir / TERRAFORM_DIR).is_dir():
        return True
    if mode == InitMode.NEVER:
        return False
    dir_settings = settings.model_copy(update={"work_dir": tf_dir})
    init_result = init(InitInput(settings=dir_settings))
    if init_result.exit_code != 0:
        logger.warning(f"init failed in {tf_dir}, skipping validate")
        return False
    return True


def _check_directory(
    tf_dir: Path,
    resolved_binary: str,
    fix: bool,
    diff: bool,
    init_mode: InitMode,
    settings: TfDoSettings,
) -> _DirRunResult:
    fmt = _run_fmt(resolved_binary, tf_dir, fix, diff)
    if not _ensure_initialized(tf_dir, init_mode, settings):
        return _DirRunResult(fmt=fmt, validation_errors=[], skipped=True)
    errors = _run_validate(resolved_binary, tf_dir)
    return _DirRunResult(fmt=fmt, validation_errors=errors, skipped=False)


def check(input_model: CheckInput) -> CheckResult:
    settings = input_model.settings
    resolved_binary = binary.resolve_binary(settings)

    tf_dirs = find_tf_directories(
        settings.work_dir,
        include_patterns=input_model.include_patterns or None,
        exclude_patterns=input_model.exclude_patterns or None,
    )

    run_results: dict[Path, _DirRunResult] = {}
    with run_pool(task_name="tfdo check", total=len(tf_dirs)) as pool:
        futures = {
            tf_dir: pool.submit(
                _check_directory,
                tf_dir,
                resolved_binary,
                input_model.fix,
                input_model.diff,
                input_model.init_mode,
                settings,
            )
            for tf_dir in tf_dirs
        }
        for tf_dir, future in futures.items():
            run_results[tf_dir] = future.result()

    dir_results = [
        DirCheckResult(
            directory=tf_dir,
            fmt_files=run_result.fmt.files,
            validation_errors=run_result.validation_errors,
            skipped=run_result.skipped,
        )
        for tf_dir, run_result in run_results.items()
    ]

    has_fmt_issues = any(d.fmt_files for d in dir_results) and not input_model.fix
    has_errors = any(d.validation_errors for d in dir_results)
    exit_code = 1 if has_fmt_issues or has_errors else 0

    return CheckResult(exit_code=exit_code, dir_results=dir_results)
