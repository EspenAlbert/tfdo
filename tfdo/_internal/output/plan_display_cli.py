from tfdo._internal.output.plan_display import PlanDisplayCliOverrides


def plan_display_cli_overrides(
    *,
    show_computed_drift: bool | None = None,
    show_computed_deltas: bool | None = None,
    show_create_defaults: bool | None = None,
    show_full_config_annex: bool | None = None,
    show_json_annex: bool | None = None,
) -> PlanDisplayCliOverrides:
    return PlanDisplayCliOverrides(
        show_computed_drift=show_computed_drift,
        show_computed_deltas=show_computed_deltas,
        show_create_defaults=show_create_defaults,
        show_full_config_annex=show_full_config_annex,
        show_json_annex=show_json_annex,
    )
