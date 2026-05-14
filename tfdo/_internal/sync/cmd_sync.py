from __future__ import annotations

import logging

import typer
from ask_shell._internal.interactive import ChoiceTyped, select_list_multiple_choices

from tfdo._internal.config.config_file import load_config
from tfdo._internal.config.config_model import TfDoConfig
from tfdo._internal.sync import sync_justfile as _sync_justfile_mod
from tfdo._internal.sync.sync_justfile import SyncJustfileInput, SyncTargetGroup
from tfdo._internal.typer_app import app, get_settings

logger = logging.getLogger(__name__)

sync_app = typer.Typer(help="Sync generated repo artifacts (justfile, GitHub workflows)")
app.add_typer(sync_app, name="sync")


def _prompt_target_groups(settings_interactive: bool) -> list[SyncTargetGroup]:
    all_groups = list(SyncTargetGroup)
    choices: list[ChoiceTyped[SyncTargetGroup]] = [ChoiceTyped(name=g, value=g, checked=True) for g in all_groups]
    if not settings_interactive:
        return all_groups
    return select_list_multiple_choices("Select target groups to generate", choices, default=all_groups)


@sync_app.command("justfile")
def justfile_cmd(ctx: typer.Context) -> None:
    """Generate repo-level justfile with env-scoped Terraform targets."""
    settings = get_settings(ctx)
    config = load_config(settings.work_dir) or TfDoConfig()
    selected = _prompt_target_groups(settings.is_interactive)
    result = _sync_justfile_mod.sync_justfile(
        SyncJustfileInput(settings=settings, config=config, selected_groups=selected)
    )
    status = "updated" if result.section_updated else "unchanged"
    envs = ", ".join(result.env_names) if result.env_names else "none discovered"
    logger.info(f"sync justfile: {status} ({result.justfile_path})")
    logger.info(f"  envs: {envs}")
    logger.info(f"  targets: {', '.join(g for g in result.selected_groups)}")
