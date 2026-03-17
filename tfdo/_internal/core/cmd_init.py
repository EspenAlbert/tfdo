import logging

import typer

from tfdo._internal.typer_app import app, get_settings

logger = logging.getLogger(__name__)


@app.command("init")
@app.command("i")
def init_cmd(
    ctx: typer.Context,
    extra_args: list[str] = typer.Argument(default=None, help="Extra arguments forwarded to terraform init"),
) -> None:
    """Run terraform init with retry on transient errors."""
    settings = get_settings(ctx)
    logger.info(f"tfdo init [binary={settings.binary}] -- not implemented yet")
    raise typer.Exit(0)
