from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from tfdo._internal.output.render_thresholds import MAX_STRUCTURAL_LINES

FULL_DETAIL_MAX_INLINE_LINES = 100


class DetailLevel(StrEnum):
    COMPACT = "compact"  # default approve-friendly attribute filtering
    FULL = "full"  # investigation preset: annex, computed deltas, create defaults


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


def detail_preset(level: DetailLevel) -> PlanDisplayOptions:
    match level:
        case DetailLevel.FULL:
            return PlanDisplayOptions(
                show_full_config_annex=True,
                show_computed_deltas=True,
                show_create_defaults=True,
                max_inline_lines=FULL_DETAIL_MAX_INLINE_LINES,
            )
        case DetailLevel.COMPACT:
            return PlanDisplayOptions()


def _overlay_options(base: PlanDisplayOptions, overlay: PlanDisplayOptions) -> PlanDisplayOptions:
    return PlanDisplayOptions(
        show_computed_drift=overlay.show_computed_drift,
        show_computed_deltas=overlay.show_computed_deltas,
        show_create_defaults=overlay.show_create_defaults,
        show_full_config_annex=overlay.show_full_config_annex,
        show_json_annex=overlay.show_json_annex,
        max_inline_lines=overlay.max_inline_lines,
    )


def merge_plan_display(
    base: PlanDisplayOptions,
    user: PlanDisplayOptions | None,
    cli: PlanDisplayCliOverrides,
) -> PlanDisplayOptions:
    merged = _overlay_options(base, user) if user else base
    return PlanDisplayOptions(
        show_computed_drift=(
            cli.show_computed_drift if cli.show_computed_drift is not None else merged.show_computed_drift
        ),
        show_computed_deltas=(
            cli.show_computed_deltas if cli.show_computed_deltas is not None else merged.show_computed_deltas
        ),
        show_create_defaults=(
            cli.show_create_defaults if cli.show_create_defaults is not None else merged.show_create_defaults
        ),
        show_full_config_annex=(
            cli.show_full_config_annex if cli.show_full_config_annex is not None else merged.show_full_config_annex
        ),
        show_json_annex=(cli.show_json_annex if cli.show_json_annex is not None else merged.show_json_annex),
        max_inline_lines=(cli.max_inline_lines if cli.max_inline_lines is not None else merged.max_inline_lines),
    )
