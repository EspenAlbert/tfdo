import logging
from pathlib import Path

import typer

from tfdo._internal import cmd_options
from tfdo._internal.core import check_logic
from tfdo._internal.models import CheckInput, CheckResult, DirCheckResult, InitMode
from tfdo._internal.settings import resolve_tflint_flag
from tfdo._internal.typer_app import app, get_settings

logger = logging.getLogger(__name__)


def _log_dir(dr: DirCheckResult, work_dir: Path) -> None:
    rel = dr.directory.relative_to(work_dir)
    if dr.skipped:
        logger.warning(f"  {rel}: skipped (not initialized)")
        return
    if not dr.has_issues:
        logger.info(f"  {rel}: ok")
        return
    issues: list[str] = []
    if dr.fmt_files:
        issues.append(f"{len(dr.fmt_files)} fmt")
    if dr.validation_errors:
        issues.append(f"{len(dr.validation_errors)} validate")
    if dr.tflint_issues:
        issues.append(f"{len(dr.tflint_issues)} tflint")
    logger.error(f"  {rel}: {', '.join(issues)}")
    for f in dr.fmt_files:
        logger.error(f"    fmt: {f}")
    for err in dr.validation_errors:
        logger.error(f"    validate: {err}")
    for issue in dr.tflint_issues:
        logger.error(f"    tflint: {issue.display}")


def _log_result(result: CheckResult, work_dir: Path) -> None:
    for dr in result.dir_results:
        _log_dir(dr, work_dir)
    fmt = len(result.total_fmt_files)
    errors = len(result.total_validation_errors)
    tflint = len(result.total_tflint_issues)
    skipped = len(result.directories_skipped)
    parts = [f"{result.directories_checked} checked"]
    if fmt:
        parts.append(f"{fmt} fmt issues")
    if errors:
        parts.append(f"{errors} validation errors")
    if tflint:
        parts.append(f"{tflint} tflint issues")
    if skipped:
        parts.append(f"{skipped} skipped")
    log = logger.error if result.exit_code else logger.info
    log(f"check: {', '.join(parts)}")


@app.command("check")
@app.command("c")
def check_cmd(
    ctx: typer.Context,
    fix: bool = typer.Option(False, "--fix", help="Auto-format instead of checking"),
    diff: bool = typer.Option(False, "--diff", help="Show what would change"),
    init_mode: InitMode = cmd_options.init_mode_option(),
    include: list[str] = cmd_options.include_option(),
    exclude: list[str] = cmd_options.exclude_option(),
    tflint: bool | None = cmd_options.tflint_option(),
) -> None:
    """Run terraform fmt check + validate (ruff-style)."""
    settings = get_settings(ctx)
    tflint_enabled = resolve_tflint_flag(tflint, settings)
    input_model = CheckInput(
        settings=settings,
        fix=fix,
        diff=diff,
        init_mode=init_mode,
        include_patterns=include,
        exclude_patterns=exclude,
        tflint=tflint_enabled,
    )
    result = check_logic.check(input_model)
    _log_result(result, settings.work_dir)
    raise typer.Exit(result.exit_code)
