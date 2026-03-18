from pathlib import Path

import typer

from tfdo._internal import cmd_options
from tfdo._internal.core import executor
from tfdo._internal.models import PlanInput
from tfdo._internal.typer_app import app, get_settings


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
    input_model = PlanInput(
        settings=settings, out=out, json_output=json_output, var_file=var_file, init_first=init_first
    )
    result = executor.plan(input_model)
    raise typer.Exit(result.exit_code)
