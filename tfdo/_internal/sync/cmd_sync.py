from __future__ import annotations

import logging
import os
from pathlib import Path

import typer
from ask_shell._internal.interactive import confirm, select_list
from ask_shell.shell import ShellError, run_and_wait

from tfdo._internal.config.config_file import CONFIG_FILENAME, load_config
from tfdo._internal.config.config_model import TfDoConfig
from tfdo._internal.config.provider_hints import ProviderHints, load_provider_hints
from tfdo._internal.git_utils import is_git_repo
from tfdo._internal.sync import sync_github as _sync_github_mod
from tfdo._internal.sync import sync_justfile as _sync_justfile_mod
from tfdo._internal.sync.sync_github import SyncGithubInput
from tfdo._internal.sync.sync_justfile import SyncJustfileInput
from tfdo._internal.typer_app import app, get_settings

logger = logging.getLogger(__name__)

_GH_VISIBILITY_OPTIONS = ["private", "public"]

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
    try:
        result = run_and_wait("gh repo view --json nameWithOwner -q .nameWithOwner", skip_progress_output=True)
    except ShellError:
        return ""
    return result.stdout_one_line


def _ensure_git_repo(work_dir: Path, config: TfDoConfig) -> None:
    if is_git_repo(work_dir):
        return
    if not confirm("No git repository found. Initialize one?", default=True):
        raise typer.Abort()
    run_and_wait("git init", cwd=work_dir)
    run_and_wait(f"git add {CONFIG_FILENAME}", cwd=work_dir)
    run_and_wait("git commit -m 'Initial commit with tfdo.yaml'", cwd=work_dir)
    logger.info(f"initialized git repo in {work_dir}")
    if not confirm("Create a GitHub repository?", default=True):
        return
    ci = config.ci
    owner_repo_name = f"{ci.repo_org}/{ci.repo_name}" if ci and ci.repo_org and ci.repo_name else work_dir.name
    visibility = select_list("Repository visibility", _GH_VISIBILITY_OPTIONS, default=_GH_VISIBILITY_OPTIONS[0])
    run_and_wait(f"gh repo create {owner_repo_name} --source=. --push --{visibility}", cwd=work_dir)
    logger.info(f"created GitHub repo: {owner_repo_name} ({visibility})")


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
    _ensure_git_repo(settings.work_dir, config)
    owner_repo = _detect_owner_repo()

    env_names = [env] if env else [p.name for p in config.envs(settings.work_dir)]

    input_model = SyncGithubInput(
        settings=settings,
        config=config,
        provider_hints_registry=registry,
        selected_bundles=selected_bundles,
        env_names=env_names,
        owner_repo=owner_repo,
        os_env=dict(os.environ),
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
