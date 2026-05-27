from tfdo._internal.output.plan_display import (
    FULL_DETAIL_MAX_INLINE_LINES,
    DetailLevel,
    PlanDisplayCliOverrides,
    PlanDisplayOptions,
    detail_preset,
    merge_plan_display,
)


def test_detail_preset_full_enables_investigation_flags() -> None:
    preset = detail_preset(DetailLevel.FULL)
    assert preset.show_full_config_annex
    assert preset.show_computed_deltas
    assert preset.show_create_defaults
    assert not preset.show_computed_drift
    assert preset.max_inline_lines == FULL_DETAIL_MAX_INLINE_LINES


def test_merge_order_cli_overrides_user_and_preset() -> None:
    base = detail_preset(DetailLevel.FULL)
    user = PlanDisplayOptions(
        show_computed_drift=True,
        show_computed_deltas=True,
        show_create_defaults=True,
        show_full_config_annex=True,
        max_inline_lines=75,
    )
    cli = PlanDisplayCliOverrides(show_computed_drift=False, show_full_config_annex=False)
    merged = merge_plan_display(base, user, cli)
    assert not merged.show_computed_drift
    assert not merged.show_full_config_annex
    assert merged.show_computed_deltas
    assert merged.max_inline_lines == 75
