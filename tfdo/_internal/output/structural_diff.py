from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple

from tfdo._internal.output import display_path


class DiffPrefix(StrEnum):
    ADD = "+"
    CHANGE = "~"
    REMOVE = "-"


class DiffLine(NamedTuple):
    path: list[str | int]
    prefix: DiffPrefix
    old: object | None
    new: object | None


class BudgetResult(NamedTuple):
    lines: list[str]
    hidden_count: int


def compute_structural_diff(
    before: object | None,
    after: object | None,
) -> list[DiffLine]:
    return _walk(before, after, [])


def format_diff_line(line: DiffLine, *, budget: int) -> str:
    key = display_path.format_display_key(line.path)
    match line.prefix, line.old, line.new:
        case DiffPrefix.CHANGE, old, new if old is not None and new is not None:
            rendered = f"{DiffPrefix.CHANGE} {key}: {display_path.inline_json(old)} -> {display_path.inline_json(new)}"
        case DiffPrefix.ADD, _, new:
            rendered = f"{DiffPrefix.ADD} {key}: {display_path.inline_json(new)}"
        case DiffPrefix.REMOVE, old, _:
            rendered = f"{DiffPrefix.REMOVE} {key}: {display_path.inline_json(old)}"
        case _:
            value = line.new if line.new is not None else line.old
            rendered = f"{line.prefix} {key}: {display_path.inline_json(value)}"
    if len(rendered) <= budget:
        return rendered
    return rendered[: max(1, budget - 1)] + "…"


def apply_line_budget(lines: list[DiffLine], max_lines: int, *, budget: int) -> BudgetResult:
    if max_lines <= 0:
        return BudgetResult(lines=[], hidden_count=len(lines))
    rendered = [format_diff_line(line, budget=budget) for line in lines[:max_lines]]
    hidden = max(0, len(lines) - max_lines)
    if hidden:
        rendered.append(f"… (+{hidden} unchanged fields)")
    return BudgetResult(lines=rendered, hidden_count=hidden)


def _walk(before: object | None, after: object | None, path: list[str | int]) -> list[DiffLine]:
    if before == after:
        return []
    if before is None:
        return _emit_create(after, path)
    if after is None:
        return _emit_delete(before, path)
    match before, after:
        case dict(), dict():
            lines: list[DiffLine] = []
            for key in sorted(set(before) | set(after), key=str):
                lines.extend(_walk(before.get(key), after.get(key), [*path, key]))
            return lines
        case list(), list():
            lines = []
            for i in range(max(len(before), len(after))):
                old = before[i] if i < len(before) else None
                new = after[i] if i < len(after) else None
                lines.extend(_walk(old, new, [*path, i]))
            return lines
        case _:
            return [DiffLine(path, DiffPrefix.CHANGE, before, after)]


def _emit_create(after: object, path: list[str | int]) -> list[DiffLine]:
    match after:
        case dict() as mapping:
            lines: list[DiffLine] = []
            for key in sorted(mapping):
                lines.extend(_emit_create(mapping[key], [*path, key]))
            return lines
        case list() as items:
            lines = []
            for i, item in enumerate(items):
                lines.extend(_emit_create(item, [*path, i]))
            return lines
        case _:
            return [DiffLine(path, DiffPrefix.ADD, None, after)]


def _emit_delete(before: object, path: list[str | int]) -> list[DiffLine]:
    match before:
        case dict() as mapping:
            lines: list[DiffLine] = []
            for key in sorted(mapping):
                lines.extend(_emit_delete(mapping[key], [*path, key]))
            return lines
        case list() as items:
            lines = []
            for i, item in enumerate(items):
                lines.extend(_emit_delete(item, [*path, i]))
            return lines
        case _:
            return [DiffLine(path, DiffPrefix.REMOVE, before, None)]
