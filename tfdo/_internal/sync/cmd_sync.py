from __future__ import annotations

import logging

import typer

from tfdo._internal.config.config_file import load_config
from tfdo._internal.config.config_model import TfDoConfig
from tfdo._internal.sync import sync_justfile as _sync_justfile_mod
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
