import logging
from pathlib import Path

import typer

from tfdo._internal import cmd_options
from tfdo._internal.typer_app import app, get_settings

logger = logging.getLogger(__name__)


@app.command("destroy")
@app.command("d")
def destroy_cmd(
    ctx: typer.Context,
    auto_approve: bool = cmd_options.auto_approve_option(),
    var_file: Path | None = cmd_options.var_file_option(),
    init_first: bool = cmd_options.init_first_option(),
) -> None:
    """Run terraform destroy."""
    settings = get_settings(ctx)
    logger.info(f"tfdo destroy [binary={settings.binary}] -- not implemented yet")
    raise typer.Exit(0)
