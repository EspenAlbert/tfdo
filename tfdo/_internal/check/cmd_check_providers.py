from __future__ import annotations

import logging
import os

import typer

from tfdo._internal.check.check_run_dir import check_run_dir
from tfdo._internal.check.models import CheckResult, ProviderCheckResult
from tfdo._internal.config.config_file import load_config
from tfdo._internal.run.discovery import discover_run_dirs, parse_discovery_pattern
from tfdo._internal.typer_app import app, get_settings

logger = logging.getLogger(__name__)


def _fmt_provider(r: ProviderCheckResult) -> str:
    decl = "ok" if r.declaration.ok else f"error[{r.declaration.case}]: {r.declaration.message}"
    if r.credentials.satisfied:
        creds = f"ok ({r.credentials.satisfied_bundle})" if r.credentials.satisfied_bundle else "ok"
    else:
        missing = ", ".join(r.credentials.missing_keys)
        creds = f"missing {missing} (closest: {r.credentials.closest_bundle})"
    return f"  {r.name}: declaration={decl}  credentials={creds}"


def _print_result(label: str, result: CheckResult) -> None:
    status = "OK" if result.is_ok else "FAIL"
    logger.info(f"{label}  [{status}]")
    for p in result.providers:
        logger.info(_fmt_provider(p))


@app.command("check-providers")
def check_providers_cmd(
    ctx: typer.Context,
    path: str = typer.Option("", "--path", "-p", help="Run-dir path relative to work-dir; omit to check all"),
    env: str = typer.Option("dev", "--env", "-e", help="Environment name for config resolution"),
) -> None:
    """Validate provider declarations and credential satisfaction for one or all run-dirs."""
    settings = get_settings(ctx)
    work_dir = settings.work_dir
    os_env = dict(os.environ)
    any_fail = False

    if path:
        abs_path = (work_dir / path).resolve()
        rel = str(abs_path.relative_to(work_dir.resolve()))
        result = check_run_dir(work_dir, env, rel, os_env, settings)
        _print_result(rel, result)
        any_fail = not result.is_ok
    else:
        root_cfg = load_config(work_dir)
        if root_cfg is None or not root_cfg.run_dir_discovery:
            logger.error(
                "No run_dir_discovery pattern configured in root tfdo.yaml. Use --path to check a single run-dir."
            )
            raise typer.Exit(1)
        pattern = parse_discovery_pattern(root_cfg.run_dir_discovery)
        discovered = discover_run_dirs(work_dir, pattern, require_backend=False)
        if not discovered:
            logger.info("No run-dirs discovered.")
        for run_dir in discovered:
            run_env = run_dir.selectors.get("env", env)
            result = check_run_dir(work_dir, run_env, run_dir.relative_path, os_env, settings)
            _print_result(run_dir.relative_path, result)
            any_fail = any_fail or not result.is_ok

    if any_fail:
        raise typer.Exit(1)
