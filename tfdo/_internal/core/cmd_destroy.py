from pathlib import Path

import typer

from tfdo._internal import cmd_options
from tfdo._internal.core import executor
from tfdo._internal.models import DestroyInput, InitMode
from tfdo._internal.typer_app import app, get_settings


@app.command("destroy")
@app.command("d")
def destroy_cmd(
    ctx: typer.Context,
    auto_approve: bool = cmd_options.auto_approve_option(),
    var_file: Path | None = cmd_options.var_file_option(),
    init_mode: InitMode = cmd_options.init_mode_option(),
) -> None:
    """Run terraform destroy."""
    settings = get_settings(ctx)
    input_model = DestroyInput(settings=settings, auto_approve=auto_approve, var_file=var_file, init_mode=init_mode)
    result = executor.destroy(input_model)
    raise typer.Exit(result.exit_code)
