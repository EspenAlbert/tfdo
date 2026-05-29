from __future__ import annotations

import re
from enum import StrEnum
from typing import NamedTuple

from pydantic import BaseModel

_DURATION_PART = re.compile(r"(?P<value>\d+)(?P<unit>[smh])")


class ApplyDisplayOptions(BaseModel):
    slow_threshold: str = "2m"
    very_slow_threshold: str = "10m"
    hide_provision_output: bool = False


class ApplyDisplayCliOverrides(BaseModel):
    hide_provision_output: bool | None = None


class _SlowTier(StrEnum):
    NORMAL = "normal"
    SLOW = "slow"
    VERY_SLOW = "very_slow"


class ResolvedApplyDisplay(NamedTuple):
    options: ApplyDisplayOptions
    slow_seconds: float
    very_slow_seconds: float


def parse_duration_seconds(value: str, *, key: str) -> float:
    text = value.strip()
    if not text:
        raise ValueError(f"invalid {key}: {value!r}")
    total = 0.0
    consumed = 0
    for match in _DURATION_PART.finditer(text):
        consumed = match.end()
        amount = int(match.group("value"))
        match match.group("unit"):
            case "s":
                total += amount
            case "m":
                total += amount * 60
            case "h":
                total += amount * 3600
    if consumed != len(text):
        raise ValueError(f"invalid {key}: {value!r}")
    return total


def format_elapsed(seconds: float) -> str:
    whole = max(0, int(seconds))
    mins, secs = divmod(whole, 60)
    if mins:
        return f"{mins}m {secs:02d}s"
    return f"{secs}s"


def slow_tier(elapsed: float, slow_s: float, very_slow_s: float) -> _SlowTier:
    if elapsed >= very_slow_s:
        return _SlowTier.VERY_SLOW
    if elapsed >= slow_s:
        return _SlowTier.SLOW
    return _SlowTier.NORMAL


def merge_apply_display(
    base: ApplyDisplayOptions,
    user: ApplyDisplayOptions | None,
    cli: ApplyDisplayCliOverrides,
) -> ApplyDisplayOptions:
    merged = user or base
    hide = cli.hide_provision_output if cli.hide_provision_output is not None else merged.hide_provision_output
    return ApplyDisplayOptions(
        slow_threshold=merged.slow_threshold,
        very_slow_threshold=merged.very_slow_threshold,
        hide_provision_output=hide,
    )


def resolve_apply_display(
    base: ApplyDisplayOptions,
    user: ApplyDisplayOptions | None,
    cli: ApplyDisplayCliOverrides,
) -> ResolvedApplyDisplay:
    options = merge_apply_display(base, user, cli)
    slow_seconds = parse_duration_seconds(options.slow_threshold, key="slow_threshold")
    very_slow_seconds = parse_duration_seconds(options.very_slow_threshold, key="very_slow_threshold")
    return ResolvedApplyDisplay(options=options, slow_seconds=slow_seconds, very_slow_seconds=very_slow_seconds)
