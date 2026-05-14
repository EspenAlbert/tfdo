from __future__ import annotations

import logging
from pathlib import Path

import typer

from tfdo._internal import cmd_options
from tfdo._internal.check import check_logic
from tfdo._internal.check.models import ProviderCheckResult as ProviderResult
from tfdo._internal.config.config_file import load_config_layers
from tfdo._internal.config.config_resolution import resolve_skip_check_providers, resolve_tflint
from tfdo._internal.models import CheckInput, CheckResult, DirCheckResult, InitMode
from tfdo._internal.typer_app import app, get_settings

logger = logging.getLogger(__name__)


def _log_provider(r: ProviderResult) -> None:
    decl = "ok" if r.declaration.ok else f"error[{r.declaration.case}]: {r.declaration.message}"
    if r.credentials.satisfied:
        creds = f"ok ({r.credentials.satisfied_bundle})" if r.credentials.satisfied_bundle else "ok"
    else:
        missing = ", ".join(r.credentials.missing_keys)
        creds = f"missing {missing} (closest: {r.credentials.closest_bundle})"
    logger.info(f"    {r.name}: declaration={decl}  credentials={creds}")


def _log_dir_issues(dr: DirCheckResult) -> None:
    for f in dr.fmt_files:
        logger.error(f"    fmt: {f}")
    for err in dr.validation_errors:
        logger.error(f"    validate: {err}")
    for issue in dr.tflint_issues:
        logger.error(f"    tflint: {issue.display}")
    if dr.missing_tfvars:
        logger.error(f"    tfvars: missing {', '.join(dr.missing_tfvars)}")
    if dr.backend_drift:
        logger.error("    backend: backend.tf is out of sync, run 'tfdo check --fix' to update")
    if dr.provider_result is not None:
        for p in dr.provider_result.providers:
            _log_provider(p)


def _log_dir(dr: DirCheckResult) -> None:
    d = dr.directory
    if dr.skipped:
        logger.warning(f"  {d}: skipped (not initialized)")
        return
    if not dr.has_issues:
        logger.info(f"  {d}: ok")
        return
    issues: list[str] = []
    if dr.fmt_files:
        issues.append(f"{len(dr.fmt_files)} fmt")
    if dr.validation_errors:
        issues.append(f"{len(dr.validation_errors)} validate")
    if dr.tflint_issues:
        issues.append(f"{len(dr.tflint_issues)} tflint")
    if dr.missing_tfvars:
        issues.append(f"{len(dr.missing_tfvars)} tfvars")
    if dr.backend_drift:
        issues.append("backend")
    if dr.provider_result is not None and not dr.provider_result.is_ok:
        issues.append("providers")
    logger.error(f"  {d}: {', '.join(issues)}")
    _log_dir_issues(dr)


def _log_result(result: CheckResult) -> None:
    for dr in result.dir_results:
        _log_dir(dr)
    fmt = len(result.total_fmt_files)
    errors = len(result.total_validation_errors)
    tflint = len(result.total_tflint_issues)
    tfvars = sum(len(dr.missing_tfvars) for dr in result.dir_results)
    provider_failures = result.total_provider_failures
    backend_drift = sum(1 for dr in result.dir_results if dr.backend_drift)
    skipped = len(result.directories_skipped)
    parts = [f"{result.directories_checked} checked"]
    if fmt:
        parts.append(f"{fmt} fmt issues")
    if errors:
        parts.append(f"{errors} validation errors")
    if tflint:
        parts.append(f"{tflint} tflint issues")
    if tfvars:
        parts.append(f"{tfvars} missing tfvars")
    if backend_drift:
        parts.append(f"{backend_drift} backend drift")
    if provider_failures:
        parts.append(f"{provider_failures} provider issues")
    if skipped:
        parts.append(f"{skipped} skipped")
    log = logger.error if result.exit_code else logger.info
    log(f"check: {', '.join(parts)}")


def _log_next_steps(work_dir: Path) -> None:
    missing_justfile = not (work_dir / "justfile").is_file()
    missing_workflows = not (work_dir / ".github" / "workflows").is_dir()
    if not missing_justfile and not missing_workflows:
        return
    logger.info("Next steps:")
    if missing_justfile:
        logger.info("  run 'tfdo sync justfile' to generate build targets")
    if missing_workflows:
        logger.info("  run 'tfdo sync github' to scaffold CI workflows and sync secrets")


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
    skip_check_providers: bool | None = cmd_options.skip_check_providers_option(),
) -> None:
    """Run terraform fmt check + validate (ruff-style)."""
    settings = get_settings(ctx)
    layers = load_config_layers(settings.work_dir)
    tflint_enabled = resolve_tflint(tflint, settings, layers=layers)
    skip_providers = resolve_skip_check_providers(skip_check_providers, settings, layers=layers)
    input_model = CheckInput(
        settings=settings,
        fix=fix,
        diff=diff,
        init_mode=init_mode,
        include_patterns=include,
        exclude_patterns=exclude,
        tflint=tflint_enabled,
        skip_check_providers=skip_providers,
    )
    result = check_logic.check(input_model)
    _log_result(result)
    _log_next_steps(settings.work_dir)
    raise typer.Exit(result.exit_code)
