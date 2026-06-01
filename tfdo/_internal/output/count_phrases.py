from __future__ import annotations

from tfdo._internal.run.run_dir_summary import ResourceActionCounts


def apply_past_phrase(emoji: str, count: int) -> str:
    if not count:
        return ""
    match emoji:
        case "🟢":
            return f"{emoji} {count} added"
        case "🟡":
            return f"{emoji} {count} changed"
        case "🔴":
            return f"{emoji} {count} destroyed"
        case _:
            return ""


def plan_future_phrase(emoji: str, count: int) -> str:
    if not count:
        return ""
    match emoji:
        case "🟢":
            return f"{emoji} {count} to add"
        case "🟡":
            return f"{emoji} {count} to change"
        case "🔴":
            return f"{emoji} {count} to destroy"
        case "🟣":
            return f"{emoji} {count} to replace"
        case _:
            return ""


def format_apply_aggregate_phrases(counts: ResourceActionCounts) -> list[str]:
    parts = [
        apply_past_phrase("🟢", counts.add),
        apply_past_phrase("🟡", counts.change),
        apply_past_phrase("🔴", counts.destroy),
    ]
    return [part for part in parts if part]


def format_plan_aggregate_phrases(counts: ResourceActionCounts) -> list[str]:
    parts = [
        plan_future_phrase("🟢", counts.add),
        plan_future_phrase("🟡", counts.change),
        plan_future_phrase("🔴", counts.destroy),
        plan_future_phrase("🟣", counts.replace),
    ]
    return [part for part in parts if part]


def format_compact_action_tokens(counts: ResourceActionCounts, *, include_replace: bool) -> str:
    tokens: list[str] = []
    if counts.add:
        tokens.append(f"🟢{counts.add}")
    if counts.change:
        tokens.append(f"🟡{counts.change}")
    if counts.destroy:
        tokens.append(f"🔴{counts.destroy}")
    if include_replace and counts.replace:
        tokens.append(f"🟣{counts.replace}")
    return " ".join(tokens)


def sum_resource_action_counts(rows: list[ResourceActionCounts | None]) -> ResourceActionCounts | None:
    add = change = destroy = replace = 0
    seen = False
    for row in rows:
        if row is None:
            continue
        seen = True
        add += row.add
        change += row.change
        destroy += row.destroy
        replace += row.replace
    return ResourceActionCounts(add=add, change=change, destroy=destroy, replace=replace) if seen else None
