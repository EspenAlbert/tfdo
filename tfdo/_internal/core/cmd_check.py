import typer

from tfdo._internal import cmd_options
from tfdo._internal.core import check_logic
from tfdo._internal.models import CheckInput, InitMode
from tfdo._internal.typer_app import app, get_settings


@app.command("check")
@app.command("c")
def check_cmd(
    ctx: typer.Context,
    fix: bool = typer.Option(False, "--fix", help="Auto-format instead of checking"),
    diff: bool = typer.Option(False, "--diff", help="Show what would change"),
    init_mode: InitMode = cmd_options.init_mode_option(),
) -> None:
    """Run terraform fmt check + validate (ruff-style)."""
    settings = get_settings(ctx)
    input_model = CheckInput(settings=settings, fix=fix, diff=diff, init_mode=init_mode)
    result = check_logic.check(input_model)
    raise typer.Exit(result.exit_code)
