from pathlib import Path

import typer

from tfdo._internal import cmd_options
from tfdo._internal.core import apply_logic
from tfdo._internal.models import ApplyInput, InitMode
from tfdo._internal.output.plan_display_cli import plan_display_cli_overrides
from tfdo._internal.typer_app import app, get_settings


@app.command("apply")
@app.command("a")
def apply_cmd(
    ctx: typer.Context,
    auto_approve: bool = cmd_options.auto_approve_option(),
    var_file: Path | None = cmd_options.var_file_option(),
    init_mode: InitMode = cmd_options.init_mode_option(),
    show_computed_drift: bool | None = typer.Option(None, "--show-computed-drift"),
    show_computed_deltas: bool | None = typer.Option(None, "--show-computed-deltas"),
    show_create_defaults: bool | None = typer.Option(None, "--show-create-defaults"),
    show_full_config_annex: bool | None = typer.Option(None, "--show-full-config-annex"),
    show_json_annex: bool | None = typer.Option(None, "--show-json-annex"),
) -> None:
    """Run terraform apply."""
    settings = get_settings(ctx)
    input_model = ApplyInput(
        settings=settings,
        auto_approve=auto_approve,
        var_file=var_file,
        init_mode=init_mode,
        plan_display_cli=plan_display_cli_overrides(
            show_computed_drift=show_computed_drift,
            show_computed_deltas=show_computed_deltas,
            show_create_defaults=show_create_defaults,
            show_full_config_annex=show_full_config_annex,
            show_json_annex=show_json_annex,
        ),
    )
    result = apply_logic.run_apply(input_model)
    raise typer.Exit(result.exit_code)
