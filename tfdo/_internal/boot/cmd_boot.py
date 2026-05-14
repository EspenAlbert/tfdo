from __future__ import annotations

import logging

import typer

from tfdo._internal.boot.boot_repo import TfdoBootInput, boot_repo
from tfdo._internal.typer_app import app, get_settings

logger = logging.getLogger(__name__)


@app.command("boot")
def boot_cmd(
    ctx: typer.Context,
    oidc: bool = typer.Option(False, "--oidc/--no-oidc", help="Provision GitHub OIDC provider and per-env IAM roles"),
) -> None:
    """Bootstrap a new tfdo-managed Terraform repo."""
    settings = get_settings(ctx)
    result = boot_repo(TfdoBootInput(settings=settings, oidc=oidc))
    logger.info(f"Written: {', '.join(str(p) for p in result.written_paths)}")
