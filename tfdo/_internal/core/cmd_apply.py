from pathlib import Path

import typer

from tfdo._internal import cmd_options
from tfdo._internal.core import executor
from tfdo._internal.models import ApplyInput
from tfdo._internal.typer_app import app, get_settings


@app.command("apply")
@app.command("a")
def apply_cmd(
    ctx: typer.Context,
    auto_approve: bool = cmd_options.auto_approve_option(),
    var_file: Path | None = cmd_options.var_file_option(),
    init_first: bool = cmd_options.init_first_option(),
) -> None:
    """Run terraform apply."""
    settings = get_settings(ctx)
    input_model = ApplyInput(settings=settings, auto_approve=auto_approve, var_file=var_file, init_first=init_first)
    result = executor.apply(input_model)
    raise typer.Exit(result.exit_code)
