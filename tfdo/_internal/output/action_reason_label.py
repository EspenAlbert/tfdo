from __future__ import annotations

from tfdo._internal.output.models import ResourceAction

KNOWN_ACTION_REASON_LABELS: dict[str, str] = {
    "replace_because_tainted": "tainted",
    "replace_because_cannot_update": "cannot update",
    "replace_by_request": "-replace",
    "replace_by_triggers": "replace triggers",
    "delete_because_no_resource_config": "removed from config",
    "delete_because_no_module": "module removed",
    "delete_because_wrong_repetition": "wrong instance key",
    "delete_because_count_index": "count index out of range",
    "delete_because_each_key": "for_each key removed",
    "delete_because_no_move_target": "move target missing",
    "read_because_config_unknown": "config unknown",
    "read_because_dependency_pending": "dependency pending",
    "read_because_check_nested": "nested check",
}

_REASON_PREFIXES = ("replace_because_", "delete_because_", "read_because_", "replace_by_")


def format_action_reason_label(action_reason: str | None) -> str | None:
    if not action_reason:
        return None
    if label := KNOWN_ACTION_REASON_LABELS.get(action_reason):
        return label
    for prefix in _REASON_PREFIXES:
        if action_reason.startswith(prefix):
            remainder = action_reason.removeprefix(prefix)
            if remainder:
                return remainder.replace("_", " ")
            return None
    return action_reason.replace("_", " ")


def format_replace_order_label(action: ResourceAction) -> str | None:
    match action:
        case ResourceAction.REPLACE_DESTROY_FIRST:
            return "destroy before create"
        case ResourceAction.REPLACE_CREATE_FIRST:
            return "create before destroy"
        case _:
            return None


def format_resource_suffix_clauses(action: ResourceAction, *, action_reason: str | None) -> list[str]:
    clauses: list[str] = []
    if label := format_action_reason_label(action_reason):
        clauses.append(label)
    match action:
        case ResourceAction.REPLACE_DESTROY_FIRST | ResourceAction.REPLACE_CREATE_FIRST:
            if order := format_replace_order_label(action):
                clauses.append(order)
        case _:
            pass
    return clauses
