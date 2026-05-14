from __future__ import annotations

import logging
import os

import typer
from ask_shell._internal.interactive import select_list
from ask_shell.shell import run_and_wait

from tfdo._internal.config.config_file import load_config, load_optional_env_vars_from_files
from tfdo._internal.config.config_model import TfDoConfig
from tfdo._internal.config.provider_hints import ProviderHints, load_provider_hints
from tfdo._internal.sync import sync_github as _sync_github_mod
from tfdo._internal.sync import sync_justfile as _sync_justfile_mod
from tfdo._internal.sync.sync_github import SyncGithubInput
from tfdo._internal.sync.sync_justfile import SyncJustfileInput
from tfdo._internal.typer_app import app, get_settings

logger = logging.getLogger(__name__)

sync_app = typer.Typer(help="Sync generated repo artifacts (justfile, GitHub workflows)")
app.add_typer(sync_app, name="sync")


@sync_app.command("justfile")
def justfile_cmd(ctx: typer.Context) -> None:
    """Generate repo-level justfile with per-env (and per-run-dir) Terraform targets."""
    settings = get_settings(ctx)
    config = load_config(settings.work_dir) or TfDoConfig()
    result = _sync_justfile_mod.sync_justfile(SyncJustfileInput(settings=settings, config=config))
    status = "updated" if result.section_updated else "unchanged"
    targets = ", ".join(result.target_names) if result.target_names else "none discovered"
    logger.info(f"sync justfile: {status} ({result.justfile_path})")
    logger.info(f"  targets: {targets}")


def _detect_owner_repo() -> str:
    result = run_and_wait("gh repo view --json nameWithOwner -q .nameWithOwner", skip_progress_output=True)
    return result.stdout_one_line


def _select_bundles(config: TfDoConfig, registry: dict[str, ProviderHints]) -> dict[str, str]:
    selected: dict[str, str] = {}
    for provider in config.providers:
        hints = registry.get(provider.name)
        if hints is None or not hints.auth_bundles:
            continue
        if len(hints.auth_bundles) == 1:
            selected[provider.name] = hints.auth_bundles[0].name
            continue
        bundle_names = [b.name for b in hints.auth_bundles]
        choice = select_list(f"Auth bundle for {provider.name}", bundle_names, default=bundle_names[0])
        selected[provider.name] = choice
    return selected


@sync_app.command("github")
@sync_app.command("gh")
def github_cmd(
    ctx: typer.Context,
    dry_run: bool = typer.Option(
        False, "--dry-run/--no-dry-run", help="Log actions without writing files or calling gh"
    ),
    env: str | None = typer.Option(None, "--env", help="Sync only this environment"),
) -> None:
    """Scaffold GitHub Actions workflows and sync secrets/variables per environment."""
    settings = get_settings(ctx)
    config = load_config(settings.work_dir) or TfDoConfig()
    registry = load_provider_hints(settings.resolved_provider_hints_path)
    selected_bundles = _select_bundles(config, registry)
    owner_repo = _detect_owner_repo()

    env_names = [env] if env else [p.name for p in config.envs(settings.work_dir)]
    file_env_vars = load_optional_env_vars_from_files(settings.work_dir, settings, log=logger)
    merged_env_vars = {**os.environ, **file_env_vars}

    input_model = SyncGithubInput(
        settings=settings,
        config=config,
        provider_hints_registry=registry,
        selected_bundles=selected_bundles,
        env_names=env_names,
        owner_repo=owner_repo,
        env_vars=merged_env_vars,
        dry_run=dry_run,
    )
    result = _sync_github_mod.sync_github(input_model)

    logger.info(f"sync github: {len(result.workflow_files)} workflow files")
    for env_result in result.env_sync_results:
        logger.info(
            f"  {env_result.env}: secrets={len(env_result.secrets_set)}, variables={len(env_result.variables_set)}"
        )
        if env_result.secrets_failed:
            logger.warning(f"  {env_result.env}: failed secrets: {', '.join(env_result.secrets_failed)}")
        if env_result.variables_failed:
            logger.warning(f"  {env_result.env}: failed variables: {', '.join(env_result.variables_failed)}")
