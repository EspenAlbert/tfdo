from __future__ import annotations

INLINE_MIN_WIDTH = 120
PER_ITEM_MIN_ITEMS = 5


def inline_budget(inline_min_width: int, terminal_width: int, indent: int) -> int:
    return max(inline_min_width, terminal_width - indent)
