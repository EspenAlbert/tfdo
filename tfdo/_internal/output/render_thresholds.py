from __future__ import annotations

INLINE_MIN_WIDTH = 120
PER_ITEM_MIN_ITEMS = 5
MAX_STRUCTURAL_LINES = 50
OUTPUT_WRAP_WIDTH = INLINE_MIN_WIDTH
OUTPUT_MULTILINE_CHARS = 400
OUTPUT_PRETTY_JSON_CHARS = 80
TREE_GUIDE_CHARS_PER_LEVEL = 4
TREE_BASE_PREFIX_CHARS = 12


def inline_budget(inline_min_width: int, terminal_width: int, indent: int) -> int:
    available = terminal_width - indent
    if available < inline_min_width:
        return max(1, available)
    return max(inline_min_width, available)
