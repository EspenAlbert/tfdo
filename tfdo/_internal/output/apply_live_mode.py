from __future__ import annotations

from enum import StrEnum

APPLY_LIVE_FULL_MAX_PARALLEL = 4
APPLY_LIVE_COMPACT_MIN_PARALLEL = 5


class ApplyLiveMode(StrEnum):
    FULL = "full"  # TTY live panel + TTY completion lines
    COMPACT = "compact"  # CI-style scroll lines, no live panel
    OFF = "off"  # Passthrough / non-streaming


def apply_status_renderable_name(run_dir_key: str) -> str:
    if not run_dir_key:
        return "apply-status"
    return f"apply-status:{run_dir_key.replace('/', ':')}"


def plan_status_renderable_name(run_dir_key: str) -> str:
    if not run_dir_key:
        return "plan-status"
    return f"plan-status:{run_dir_key.replace('/', ':')}"


def resolve_apply_live_mode(
    *,
    orchestration_active: bool,
    parallel: int,
    interactive: bool,
) -> ApplyLiveMode:
    if not interactive:
        return ApplyLiveMode.FULL
    if not orchestration_active:
        return ApplyLiveMode.FULL
    if parallel >= APPLY_LIVE_COMPACT_MIN_PARALLEL:
        return ApplyLiveMode.COMPACT
    return ApplyLiveMode.FULL
