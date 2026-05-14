from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

from ask_shell._internal.run_pool import run_pool
from ask_shell.shell import run_and_wait

from tfdo._internal.check.check_run_dir import check_run_dir
from tfdo._internal.check.models import CheckResult as RunDirProviderResult
from tfdo._internal.config import backend_resolution
from tfdo._internal.config.config_file import (
    load_config_layers,
    load_optional_env_vars_from_files,
    resolve_var_file_paths,
)
from tfdo._internal.config.config_resolution import resolve_config
from tfdo._internal.core import binary
from tfdo._internal.core.executor import init
from tfdo._internal.core.tf_files import TERRAFORM_DIR, find_tf_directories
from tfdo._internal.git_utils import parse_git_remote
from tfdo._internal.hcl_compat import hcl2_load
from tfdo._internal.models import (
    CheckInput,
    CheckResult,
    DirCheckResult,
    InitInput,
    InitMode,
    TflintIssue,
    TflintOutput,
    ValidateOutput,
)
from tfdo._internal.run.run_context import RunDirContext
from tfdo._internal.settings import TfDoSettings, load_user_config

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
    tflint_issues: list[TflintIssue]
    missing_tfvars: list[str]
    skipped: bool
    provider_result: RunDirProviderResult | None = None
    backend_drift: bool = False


def _run_fmt(resolved_binary: str, cwd: Path, fix: bool, diff: bool) -> _FmtResult:
    cmd = _build_fmt_command(resolved_binary, fix, diff)
    run = run_and_wait(cmd, cwd=cwd, allow_non_zero_exit=True, skip_binary_check=True)
    files = [] if fix else _parse_fmt_files(run.stdout)
    return _FmtResult(files=files, stdout=run.stdout)


def _run_validate(resolved_binary: str, cwd: Path) -> list[str]:
    cmd = _build_validate_command(resolved_binary)
    run = run_and_wait(cmd, cwd=cwd, allow_non_zero_exit=True, skip_binary_check=True)
    output = run.parse_output(ValidateOutput)
    return output.error_summaries


TFLINT_BINARY = "tflint"


def _tflint_available() -> bool:
    return shutil.which(TFLINT_BINARY) is not None


def _run_tflint(cwd: Path) -> list[TflintIssue]:
    cmd = f"{TFLINT_BINARY} --format json"
    run = run_and_wait(cmd, cwd=cwd, allow_non_zero_exit=True, skip_binary_check=True)
    output = run.parse_output(TflintOutput)
    for err in output.errors:
        logger.warning(f"tflint error in {cwd}: {err.message}")
    return output.issues


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


def _required_tf_vars(tf_dir: Path) -> set[str]:
    required: set[str] = set()
    for tf_file in sorted(tf_dir.glob("*.tf")):
        try:
            with tf_file.open() as file_handle:
                parsed = hcl2_load(file_handle)
        except Exception as exc:
            logger.warning(f"failed to parse variables from {tf_file}: {exc}")
            continue
        for block in parsed.get("variable", []):
            if not isinstance(block, dict):
                continue
            for name, attrs in block.items():
                if not isinstance(attrs, dict) or "default" not in attrs:
                    required.add(name)
    return required


def _tf_var_name(key: str) -> str:
    return key.removeprefix("TF_VAR_")


def _collect_env_tf_vars(tf_dir: Path, settings: TfDoSettings, os_env: Mapping[str, str]) -> set[str]:
    provided: set[str] = {_tf_var_name(name) for name in os_env if name.startswith("TF_VAR_") and _tf_var_name(name)}
    loaded_env_vars = load_optional_env_vars_from_files(tf_dir, settings, log=logger)
    for key in loaded_env_vars:
        if key.startswith("TF_VAR_"):
            provided.add(_tf_var_name(key))
    return provided


def _provided_tf_vars(tf_dir: Path, settings: TfDoSettings, os_env: Mapping[str, str]) -> set[str]:
    provided: set[str] = set()
    for var_file_path in resolve_var_file_paths(tf_dir):
        if not var_file_path.is_file():
            continue
        try:
            with var_file_path.open() as file_handle:
                parsed = hcl2_load(file_handle)
        except Exception as exc:
            logger.warning(f"failed to parse tfvars file {var_file_path}: {exc}")
            continue
        provided.update(str(key) for key in parsed)
    provided.update(_collect_env_tf_vars(tf_dir, settings, os_env))
    return provided


def _missing_tf_vars(tf_dir: Path, settings: TfDoSettings, os_env: Mapping[str, str]) -> list[str]:
    required = _required_tf_vars(tf_dir)
    if not required:
        return []
    provided = _provided_tf_vars(tf_dir, settings, os_env)
    return sorted(required - provided)


def _check_directory(
    tf_dir: Path,
    resolved_binary: str,
    fix: bool,
    diff: bool,
    init_mode: InitMode,
    settings: TfDoSettings,
    run_tflint: bool = False,
    check_providers: bool = False,
    os_env: dict[str, str] | None = None,
) -> _DirRunResult:
    fmt = _run_fmt(resolved_binary, tf_dir, fix, diff)
    missing_tfvars = _missing_tf_vars(tf_dir, settings, os_env or os.environ)
    if not _ensure_initialized(tf_dir, init_mode, settings):
        return _DirRunResult(
            fmt=fmt,
            validation_errors=[],
            tflint_issues=[],
            missing_tfvars=missing_tfvars,
            skipped=True,
        )
    errors = _run_validate(resolved_binary, tf_dir)
    tflint_issues = _run_tflint(tf_dir) if run_tflint else []
    provider_result: RunDirProviderResult | None = None
    if check_providers:
        work_dir = settings.work_dir
        try:
            rel = str(tf_dir.relative_to(work_dir))
        except ValueError:
            rel = str(tf_dir)
        provider_result = check_run_dir(work_dir, rel, os_env or os.environ, settings)
    return _DirRunResult(
        fmt=fmt,
        validation_errors=errors,
        tflint_issues=tflint_issues,
        missing_tfvars=missing_tfvars,
        skipped=False,
        provider_result=provider_result,
    )


def _check_backend_drift(tf_dir: Path, settings: TfDoSettings, fix: bool) -> bool:
    """Check if backend.tf is out of sync with the resolved backend config.

    Returns True if drift was detected (and fixed when fix=True).
    """
    work_dir = settings.work_dir
    rel = str(tf_dir.relative_to(work_dir))
    layers = load_config_layers(tf_dir)
    user_config = load_user_config(settings)
    cfg = resolve_config(layers, user_config, settings)
    if cfg.backend is None:
        return False
    remote = parse_git_remote(work_dir)
    owner = remote.org if remote else "unknown"
    repo_name = remote.repo if remote else work_dir.name
    name = rel.rsplit("/", 1)[-1]
    ctx = RunDirContext(
        name=name,
        path=rel,
        repo_owner=owner,
        repo_name=repo_name,
        tags=cfg.tags,
    )
    if fix:
        return backend_resolution.ensure_backend_tf(tf_dir, cfg.backend, ctx)
    return backend_resolution.has_backend_drift(tf_dir, cfg.backend, ctx)


def check(input_model: CheckInput) -> CheckResult:
    settings = input_model.settings
    resolved_binary = binary.resolve_binary(settings)

    run_tflint = input_model.tflint
    if run_tflint and not _tflint_available():
        logger.warning("tflint requested but not found on PATH, skipping")
        run_tflint = False

    check_providers = not input_model.skip_check_providers
    os_env = dict(os.environ)
    tf_dirs = find_tf_directories(
        settings.work_dir,
        include_patterns=input_model.include_patterns or None,
        exclude_patterns=input_model.exclude_patterns or None,
    )

    if not tf_dirs:
        logger.warning("no .tf directories found, skipping check")
        return CheckResult(exit_code=0)

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
                run_tflint,
                check_providers,
                os_env,
            )
            for tf_dir in tf_dirs
        }
        for tf_dir, future in futures.items():
            run_results[tf_dir] = future.result()

    backend_drift: dict[Path, bool] = {}
    for tf_dir in tf_dirs:
        try:
            backend_drift[tf_dir] = _check_backend_drift(tf_dir, settings, input_model.fix)
        except Exception as exc:
            logger.warning(f"backend drift check failed for {tf_dir}: {exc}")
            backend_drift[tf_dir] = False

    dir_results = [
        DirCheckResult(
            directory=tf_dir,
            fmt_files=run_result.fmt.files,
            validation_errors=run_result.validation_errors,
            tflint_issues=run_result.tflint_issues,
            missing_tfvars=run_result.missing_tfvars,
            provider_result=run_result.provider_result,
            skipped=run_result.skipped,
            backend_drift=backend_drift.get(tf_dir, False) and not input_model.fix,
        )
        for tf_dir, run_result in run_results.items()
    ]

    has_fmt_issues = any(d.fmt_files for d in dir_results) and not input_model.fix
    has_errors = any(d.validation_errors for d in dir_results)
    has_tflint = any(d.tflint_issues for d in dir_results)
    has_missing_tfvars = any(d.missing_tfvars for d in dir_results)
    has_provider_failures = any(d.provider_result is not None and not d.provider_result.is_ok for d in dir_results)
    has_backend_drift = any(d.backend_drift for d in dir_results)
    exit_code = (
        1
        if has_fmt_issues
        or has_errors
        or has_tflint
        or has_missing_tfvars
        or has_provider_failures
        or has_backend_drift
        else 0
    )

    return CheckResult(exit_code=exit_code, dir_results=dir_results)
