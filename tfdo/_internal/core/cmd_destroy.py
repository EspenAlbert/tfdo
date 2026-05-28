from pathlib import Path

import typer

from tfdo._internal import cmd_options
from tfdo._internal.core import destroy_logic
from tfdo._internal.models import DestroyInput, InitMode
from tfdo._internal.output.plan_display import DetailLevel
from tfdo._internal.typer_app import app, get_settings


@app.command("destroy")
@app.command("d")
def destroy_cmd(
    ctx: typer.Context,
    auto_approve: bool = cmd_options.auto_approve_option(),
    var_file: Path | None = cmd_options.var_file_option(),
    init_mode: InitMode = cmd_options.init_mode_option(),
    show_computed_drift: bool | None = cmd_options.show_computed_drift_option(),
    show_computed_deltas: bool | None = cmd_options.show_computed_deltas_option(),
    show_create_defaults: bool | None = cmd_options.show_create_defaults_option(),
    show_full_config_annex: bool | None = cmd_options.show_full_config_annex_option(),
    show_json_annex: bool | None = cmd_options.show_json_annex_option(),
    detail: DetailLevel = cmd_options.detail_option(),
) -> None:
    """Run terraform destroy."""
    settings = get_settings(ctx)
    input_model = DestroyInput(
        settings=settings,
        auto_approve=auto_approve,
        var_file=var_file,
        init_mode=init_mode,
        detail=detail,
        plan_display_cli=cmd_options.plan_display_cli_overrides(
            show_computed_drift=show_computed_drift,
            show_computed_deltas=show_computed_deltas,
            show_create_defaults=show_create_defaults,
            show_full_config_annex=show_full_config_annex,
            show_json_annex=show_json_annex,
        ),
    )
    result = destroy_logic.run_destroy(input_model)
    raise typer.Exit(result.exit_code)
