import logging
from pathlib import Path

import typer

from tfdo._internal import cmd_options
from tfdo._internal.typer_app import app, get_settings

logger = logging.getLogger(__name__)


@app.command("plan")
@app.command("p")
def plan_cmd(
    ctx: typer.Context,
    out: Path | None = typer.Option(None, "-o", "--out", help="Write the plan to a file"),
    json_output: bool = typer.Option(False, "--json", help="Output plan in JSON format"),
    var_file: Path | None = cmd_options.var_file_option(),
    init_first: bool = cmd_options.init_first_option(),
) -> None:
    """Run terraform plan."""
    settings = get_settings(ctx)
    logger.info(f"tfdo plan [binary={settings.binary}] -- not implemented yet")
    raise typer.Exit(0)
