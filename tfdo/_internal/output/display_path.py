from __future__ import annotations

import json

from tfdo._internal.output.render_thresholds import INLINE_MIN_WIDTH, PER_ITEM_MIN_ITEMS


def path_get_value(data: dict[str, object] | None, path: list[str | int]) -> object | None:
    if data is None:
        return None
    current: object = data
    for part in path:
        match current, part:
            case dict(), str() as key:
                current = current.get(key)
            case list(), int() as index:
                if index < 0 or index >= len(current):
                    return None
                current = current[index]
            case _:
                return None
    return current


def inline_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def inline_json_fits(value: object, budget: int = INLINE_MIN_WIDTH) -> bool:
    return len(inline_json(value)) <= budget


def per_item_trigger(
    items: list[object],
    *,
    min_items: int = PER_ITEM_MIN_ITEMS,
    budget: int = INLINE_MIN_WIDTH,
) -> bool:
    return len(items) >= min_items or not inline_json_fits(items, budget)


def is_flat_collection_item(item: object) -> bool:
    match item:
        case dict() | str() | int() | float() | bool() | None:
            return True
        case _:
            return False


def format_display_key(path: list[str | int]) -> str:
    if not path:
        return ""
    parts: list[str] = []
    i = 0
    while i < len(path):
        seg = path[i]
        if isinstance(seg, str):
            label = seg
            if i + 1 < len(path) and isinstance(path[i + 1], int):
                label = f"{seg}[{path[i + 1]}]"
                i += 2
            else:
                i += 1
            parts.append(label)
        else:
            i += 1
    return parts[0] if len(parts) == 1 else ".".join(parts)


def values_for_display_key(
    key: str,
    before: dict[str, object],
    after: dict[str, object],
) -> tuple[object | None, object | None]:
    if "[" not in key and "." not in key:
        return before.get(key), after.get(key)
    path = parse_display_key(key)
    return path_get_value(before, path), path_get_value(after, path)


def _root_attribute_value(
    root: str,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
) -> object | None:
    return path_get_value(after, [root]) or path_get_value(before, [root])


def _index_position(path: list[str | int]) -> int | None:
    for i, part in enumerate(path):
        if isinstance(part, int):
            return i
    return None


def _per_item_display(items: list[object]) -> bool:
    return per_item_trigger(items)


def _indexed_replace_display_key(
    path: list[str | int],
    *,
    prefix: list[str | int],
    before: dict[str, object] | None,
    after: dict[str, object] | None,
) -> str:
    item_val = path_get_value(after, prefix) or path_get_value(before, prefix)
    match item_val, path[-1]:
        case dict(), str() if not inline_json_fits(item_val):
            return format_display_key(path)
        case _:
            return format_display_key(prefix)


def replace_display_key(
    path: list[str | int],
    before: dict[str, object] | None,
    after: dict[str, object] | None,
) -> str:
    match path:
        case [str() as name]:
            return name

    root = path[0]
    if not isinstance(root, str):
        return format_display_key(path)

    root_val = _root_attribute_value(root, before, after)
    tail = path[1:]

    match tail:
        case [str(), *_] if isinstance(root_val, dict):
            return root
        case _ if (idx := _index_position(path)) is not None:
            prefix = path[: idx + 1]
            match root_val:
                case list() as items if _per_item_display(items):
                    return _indexed_replace_display_key(path, prefix=prefix, before=before, after=after)
                case list() | dict() if inline_json_fits(root_val):
                    return root
                case _:
                    return format_display_key(prefix)
        case _:
            return format_display_key(path)


def resolve_replace_display_keys(
    replace_paths: list[list[str | int]] | None,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
) -> set[str]:
    if not replace_paths:
        return set()
    deepest = _drop_shallow_paths(replace_paths)
    return {replace_display_key(path, before, after) for path in deepest}


def parse_display_key(key: str) -> list[str | int]:
    path: list[str | int] = []
    for segment in key.split("."):
        if "[" in segment:
            name, rest = segment.split("[", 1)
            index = int(rest.rstrip("]"))
            path.extend([name, index])
        else:
            path.append(segment)
    return path


def _is_prefix(shorter: list[str | int], longer: list[str | int]) -> bool:
    return len(shorter) < len(longer) and list(shorter) == list(longer[: len(shorter)])


def _drop_shallow_paths(paths: list[list[str | int]]) -> list[list[str | int]]:
    return [path for path in paths if not any(_is_prefix(path, other) for other in paths if other is not path)]
