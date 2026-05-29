from __future__ import annotations

from typing import NamedTuple

from tfdo._internal.output.models import ResourceAction

_REPLACE_ACTIONS = frozenset(
    {
        ResourceAction.REPLACE_DESTROY_FIRST,
        ResourceAction.REPLACE_CREATE_FIRST,
    }
)
_HOOK_REPLACE_KEYS = frozenset({"replace", "delete+create", "create+delete"})


class ApplyDisplayVerbs(NamedTuple):
    present: str
    past: str


def display_verbs_for_hook_action(action: str) -> ApplyDisplayVerbs:
    match action:
        case "create":
            return ApplyDisplayVerbs("creating", "created")
        case "update":
            return ApplyDisplayVerbs("modifying", "modified")
        case "delete":
            return ApplyDisplayVerbs("destroying", "destroyed")
        case _ if action in _HOOK_REPLACE_KEYS:
            return ApplyDisplayVerbs("replacing", "replaced")
        case _:
            return ApplyDisplayVerbs("applying", "applied")


def display_verbs_for_resource_action(action: ResourceAction) -> ApplyDisplayVerbs:
    if action in _REPLACE_ACTIONS:
        return ApplyDisplayVerbs("replacing", "replaced")
    return display_verbs_for_hook_action(action)
