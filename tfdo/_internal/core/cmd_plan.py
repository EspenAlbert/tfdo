from pathlib import Path

import typer

from tfdo._internal import cmd_options
from tfdo._internal.core import plan_logic
from tfdo._internal.models import InitMode, PlanInput
from tfdo._internal.typer_app import app, get_settings


@app.command("plan")
@app.command("p")
def plan_cmd(
    ctx: typer.Context,
    out: Path | None = typer.Option(None, "-o", "--out", help="Write the plan to a file"),
    json_output: bool = typer.Option(False, "--json", help="Output plan in JSON format"),
    var_file: Path | None = cmd_options.var_file_option(),
    init_mode: InitMode = cmd_options.init_mode_option(),
    show_computed_drift: bool | None = cmd_options.show_computed_drift_option(),
    show_computed_deltas: bool | None = cmd_options.show_computed_deltas_option(),
    show_create_defaults: bool | None = cmd_options.show_create_defaults_option(),
    show_full_config_annex: bool | None = cmd_options.show_full_config_annex_option(),
    show_json_annex: bool | None = cmd_options.show_json_annex_option(),
) -> None:
    """Run terraform plan."""
    settings = get_settings(ctx)
    input_model = PlanInput(
        settings=settings,
        out=out,
        json_output=json_output,
        var_file=var_file,
        init_mode=init_mode,
        plan_display_cli=cmd_options.plan_display_cli_overrides(
            show_computed_drift=show_computed_drift,
            show_computed_deltas=show_computed_deltas,
            show_create_defaults=show_create_defaults,
            show_full_config_annex=show_full_config_annex,
            show_json_annex=show_json_annex,
        ),
    )
    result = plan_logic.run_plan(input_model)
    raise typer.Exit(result.exit_code)
