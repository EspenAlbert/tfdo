from __future__ import annotations

from pydantic import BaseModel

from tfdo._internal.output.render_thresholds import MAX_STRUCTURAL_LINES


class PlanDisplayOptions(BaseModel):
    show_computed_drift: bool = False
    show_computed_deltas: bool = False
    show_create_defaults: bool = False
    show_full_config_annex: bool = False
    show_json_annex: bool = False
    max_inline_lines: int = MAX_STRUCTURAL_LINES


class PlanDisplayCliOverrides(BaseModel):
    show_computed_drift: bool | None = None
    show_computed_deltas: bool | None = None
    show_create_defaults: bool | None = None
    show_full_config_annex: bool | None = None
    show_json_annex: bool | None = None
    max_inline_lines: int | None = None


def merge_plan_display(
    user: PlanDisplayOptions | None,
    cli: PlanDisplayCliOverrides,
) -> PlanDisplayOptions:
    base = user or PlanDisplayOptions()
    return PlanDisplayOptions(
        show_computed_drift=(
            cli.show_computed_drift if cli.show_computed_drift is not None else base.show_computed_drift
        ),
        show_computed_deltas=(
            cli.show_computed_deltas if cli.show_computed_deltas is not None else base.show_computed_deltas
        ),
        show_create_defaults=(
            cli.show_create_defaults if cli.show_create_defaults is not None else base.show_create_defaults
        ),
        show_full_config_annex=(
            cli.show_full_config_annex if cli.show_full_config_annex is not None else base.show_full_config_annex
        ),
        show_json_annex=(cli.show_json_annex if cli.show_json_annex is not None else base.show_json_annex),
        max_inline_lines=(cli.max_inline_lines if cli.max_inline_lines is not None else base.max_inline_lines),
    )
