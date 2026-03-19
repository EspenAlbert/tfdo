from __future__ import annotations

import logging
from pathlib import Path
from typing import NamedTuple

from ask_shell.shell import ShellError, run_and_wait

from tfdo._internal.core import binary
from tfdo._internal.core.executor import init
from tfdo._internal.core.tf_files import TERRAFORM_DIR, find_tf_directories
from tfdo._internal.models import CheckInput, CheckResult, InitInput, InitMode, ValidateOutput
from tfdo._internal.settings import TfDoSettings

logger = logging.getLogger(__name__)


def _build_fmt_command(resolved_binary: str, fix: bool, diff: bool) -> str:
    parts = [resolved_binary, "fmt"]
    if not fix:
        parts.append("-check")
    if diff:
        parts.append("-diff")
    parts.extend(["-recursive", "."])
    return " ".join(parts)


def _parse_fmt_stdout(stdout: str) -> int:
    if not stdout.strip():
        return 0
    return len([line for line in stdout.strip().splitlines() if line.strip()])


def _build_validate_command(resolved_binary: str) -> str:
    return f"{resolved_binary} validate -json"


class _FmtResult(NamedTuple):
    issues: int
    stdout: str


def _run_fmt(settings: TfDoSettings, resolved_binary: str, fix: bool, diff: bool) -> _FmtResult:
    cmd = _build_fmt_command(resolved_binary, fix, diff)
    try:
        run = run_and_wait(cmd, cwd=settings.work_dir, allow_non_zero_exit=True, skip_binary_check=True)
        issues = 0 if fix else _parse_fmt_stdout(run.stdout)
        return _FmtResult(issues=issues, stdout=run.stdout)
    except ShellError as e:
        issues = 0 if fix else _parse_fmt_stdout(e.run.stdout)
        return _FmtResult(issues=issues, stdout=e.run.stdout)


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


def check(input_model: CheckInput) -> CheckResult:
    settings = input_model.settings
    resolved_binary = binary.resolve_binary(settings)

    fmt_result = _run_fmt(settings, resolved_binary, input_model.fix, input_model.diff)

    tf_dirs = find_tf_directories(settings.work_dir)
    all_errors: list[str] = []
    checked = 0
    skipped: list[Path] = []

    for tf_dir in tf_dirs:
        if not _ensure_initialized(tf_dir, input_model.init_mode, settings):
            skipped.append(tf_dir)
            continue
        errors = _run_validate(resolved_binary, tf_dir)
        all_errors.extend(errors)
        checked += 1

    has_fmt_issues = fmt_result.issues > 0 and not input_model.fix
    exit_code = 1 if has_fmt_issues or all_errors else 0

    return CheckResult(
        exit_code=exit_code,
        fmt_issues=fmt_result.issues,
        validation_errors=all_errors,
        directories_checked=checked,
        directories_skipped=skipped,
    )
