from __future__ import annotations

import json
from enum import StrEnum
from typing import NamedTuple

from pydantic import BaseModel

from tfdo._internal.output import display_path
from tfdo._internal.output.render_thresholds import (
    INLINE_MIN_WIDTH,
    PER_ITEM_MIN_ITEMS,
    inline_budget,
)
from tfdo._internal.output.schema_lookup import CollectionKind


class _RenderTier(StrEnum):
    INLINE = "inline"  # compact sorted-keys JSON when the value fits the inline budget
    PER_ITEM = "per_item"  # per-element diff for flat lists (set or positional list matching)
    DETAIL = "detail"  # hoisted block above the plan; tree line shows (see above)


class _PerItemKind(StrEnum):
    CONTEXT = "context"  # unchanged element; no +/-/~ marker
    ADD = "add"  # new element
    REMOVE = "remove"  # dropped element
    CHANGE = "change"  # same index or set slot, different value


class ComplexRenderConfig(BaseModel):
    inline_min_width: int = INLINE_MIN_WIDTH
    per_item_min_items: int = PER_ITEM_MIN_ITEMS


class DetailBlock(BaseModel):
    header: str
    body_lines: list[str]


class ComplexRenderResult(BaseModel):
    inline_lines: list[str]
    detail_block: DetailBlock | None = None


class _PerItemRow(NamedTuple):
    kind: _PerItemKind
    idx: int | None
    old: object | None
    new: object | None


def render_complex_value(
    old: object | None,
    new: object | None,
    *,
    attr_name: str,
    resource_address: str,
    indent: int,
    terminal_width: int,
    config: ComplexRenderConfig,
    collection_kind: CollectionKind | None = None,
    is_sensitive: bool = False,
) -> ComplexRenderResult:
    pad = " " * indent
    if is_sensitive:
        return ComplexRenderResult(inline_lines=[f"{pad}(sensitive)"])

    budget = inline_budget(config.inline_min_width, terminal_width, indent)
    tier = _choose_tier(old, new, budget, config)
    if tier is _RenderTier.INLINE:
        return ComplexRenderResult(inline_lines=_pad_lines(_render_inline(old, new), pad))

    if tier is _RenderTier.PER_ITEM:
        per_item = _render_per_item(
            old,
            new,
            attr_name=attr_name,
            budget=budget,
            collection_kind=collection_kind,
        )
        if per_item is not None:
            return ComplexRenderResult(inline_lines=_pad_lines(per_item, pad))

    inline, block = _render_detail_block(
        old,
        new,
        attr_name=attr_name,
        resource_address=resource_address,
    )
    return ComplexRenderResult(
        inline_lines=[f"{pad}(see above)"],
        detail_block=block,
    )


def _pad_lines(lines: list[str], pad: str) -> list[str]:
    if not pad:
        return lines
    return [f"{pad}{line}" for line in lines]


def _choose_tier(
    old: object | None,
    new: object | None,
    budget: int,
    config: ComplexRenderConfig,
) -> _RenderTier:
    if _inline_tier_applies(old, new, budget):
        return _RenderTier.INLINE
    if _per_item_eligible(old, new, budget, config):
        return _RenderTier.PER_ITEM
    return _RenderTier.DETAIL


def _inline_tier_applies(old: object | None, new: object | None, budget: int) -> bool:
    if old is not None and new is not None:
        return display_path.inline_json_fits(old, budget) and display_path.inline_json_fits(new, budget)
    if new is not None:
        return display_path.inline_json_fits(new, budget)
    if old is not None:
        return display_path.inline_json_fits(old, budget)
    return True


def _render_inline(old: object | None, new: object | None) -> list[str]:
    if old is not None and new is not None:
        return [display_path.inline_json(old), f"-> {display_path.inline_json(new)}"]
    if new is not None:
        return [display_path.inline_json(new)]
    if old is not None:
        return [display_path.inline_json(old)]
    return []


def _list_side(value: object | None) -> list[object]:
    return value if isinstance(value, list) else []


def _per_item_eligible(
    old: object | None,
    new: object | None,
    budget: int,
    config: ComplexRenderConfig,
) -> bool:
    before = _list_side(old)
    after = _list_side(new)
    if not before and not after:
        return False
    combined = before + after
    if not all(display_path.is_flat_collection_item(item) for item in combined):
        return False
    return display_path.per_item_trigger(
        before,
        min_items=config.per_item_min_items,
        budget=budget,
    ) or display_path.per_item_trigger(
        after,
        min_items=config.per_item_min_items,
        budget=budget,
    )


def _render_per_item(
    old: object | None,
    new: object | None,
    *,
    attr_name: str,
    budget: int,
    collection_kind: CollectionKind | None,
) -> list[str] | None:
    before = _list_side(old)
    after = _list_side(new)
    rows = _match_set_items(before, after) if collection_kind == "set" else _match_list_items(before, after)
    lines: list[str] = []
    for row in rows:
        chunk = _format_per_item_row(row, attr_name=attr_name, budget=budget)
        if chunk is None:
            return None
        lines.extend(chunk)
    return lines


def _match_set_items(before: list[object], after: list[object]) -> list[_PerItemRow]:
    after_remaining = list(after)
    rows: list[_PerItemRow] = []
    for item in before:
        try:
            idx = after_remaining.index(item)
            after_remaining.pop(idx)
            rows.append(_PerItemRow(_PerItemKind.CONTEXT, None, item, item))
        except ValueError:
            rows.append(_PerItemRow(_PerItemKind.REMOVE, None, item, None))
    for item in after_remaining:
        rows.append(_PerItemRow(_PerItemKind.ADD, None, None, item))
    return rows


def _match_list_items(before: list[object], after: list[object]) -> list[_PerItemRow]:
    rows: list[_PerItemRow] = []
    for i in range(max(len(before), len(after))):
        old_item = before[i] if i < len(before) else None
        new_item = after[i] if i < len(after) else None
        if old_item is None:
            rows.append(_PerItemRow(_PerItemKind.ADD, i, None, new_item))
        elif new_item is None:
            rows.append(_PerItemRow(_PerItemKind.REMOVE, i, old_item, None))
        elif old_item == new_item:
            rows.append(_PerItemRow(_PerItemKind.CONTEXT, i, old_item, new_item))
        else:
            rows.append(_PerItemRow(_PerItemKind.CHANGE, i, old_item, new_item))
    return rows


def _format_item_value(item: object) -> str:
    return display_path.inline_json(item)


def _indexed_key(attr_name: str, idx: int) -> str:
    return display_path.format_display_key([attr_name, idx])


def _lines_fit(lines: list[str], budget: int) -> bool:
    return all(len(line) <= budget for line in lines)


def _format_per_item_row(
    row: _PerItemRow,
    *,
    attr_name: str,
    budget: int,
) -> list[str] | None:
    value = row.new if row.new is not None else row.old
    assert value is not None or row.kind in (
        _PerItemKind.REMOVE,
        _PerItemKind.ADD,
        _PerItemKind.CHANGE,
    )

    match row.kind, row.idx:
        case _PerItemKind.CONTEXT, None | int():
            lines = [f"  {_format_item_value(value)}"]
        case _PerItemKind.ADD, None:
            lines = [f"+ {_format_item_value(value)}"]
        case _PerItemKind.REMOVE, None:
            lines = [f"- {_format_item_value(value)}"]
        case _PerItemKind.ADD, int() as idx:
            lines = [f"+ {_indexed_key(attr_name, idx)}:", f"  {_format_item_value(value)}"]
        case _PerItemKind.REMOVE, int() as idx:
            lines = [f"- {_indexed_key(attr_name, idx)}:", f"  {_format_item_value(value)}"]
        case _PerItemKind.CHANGE, int() as idx:
            assert row.old is not None and row.new is not None
            lines = [
                f"~ {_indexed_key(attr_name, idx)}:",
                f"  {_format_item_value(row.old)}",
                f"      -> {_format_item_value(row.new)}",
            ]
        case _:
            return None

    if not _lines_fit(lines, budget):
        return None
    return lines


def _render_detail_block(
    old: object | None,
    new: object | None,
    *,
    attr_name: str,
    resource_address: str,
) -> tuple[list[str], DetailBlock]:
    header = f"--- {attr_name} ({resource_address}) ---"
    body = _detail_body_lines(old, new)
    block = DetailBlock(header=header, body_lines=[header, *body])
    return [], block


def _detail_body_lines(old: object | None, new: object | None) -> list[str]:
    lines: list[str] = []
    if isinstance(old, str) and "\n" in old:
        lines.extend(_literal_block("before", old))
    elif old is not None:
        lines.append(f"before: {_detail_value(old)}")
    if isinstance(new, str) and "\n" in new:
        lines.extend(_literal_block("after", new))
    elif new is not None:
        lines.append(f"after: {_detail_value(new)}")
    return lines


def _literal_block(label: str, text: str) -> list[str]:
    body = text.splitlines()
    return [f"{label}: |", *[f"  {line}" for line in body]]


def _detail_value(value: object) -> str:
    match value:
        case dict() | list():
            return json.dumps(value, sort_keys=True, indent=2)
        case _:
            return display_path.inline_json(value)
