from __future__ import annotations

from tfdo._internal.output import display_path
from tfdo._internal.output.plan_filters import KNOWN_AFTER_APPLY

SENSITIVE = "(sensitive)"


def format_scalar(value: object) -> str:
    if value == KNOWN_AFTER_APPLY:
        return KNOWN_AFTER_APPLY
    return display_path.inline_json(value)
