from __future__ import annotations

from tfdo._internal.output.action_reason_label import (
    format_action_reason_label,
    format_replace_order_label,
    format_resource_suffix_clauses,
)
from tfdo._internal.output.models import ResourceAction


def test_known_action_reason_labels() -> None:
    assert format_action_reason_label("replace_because_tainted") == "tainted"
    assert format_action_reason_label("delete_because_no_resource_config") == "removed from config"


def test_unknown_action_reason_fallback() -> None:
    assert format_action_reason_label("replace_because_new_reason") == "new reason"
    assert format_action_reason_label("some_other_code") == "some other code"
    assert format_action_reason_label("replace_because_") is None


def test_replace_order_labels() -> None:
    assert format_replace_order_label(ResourceAction.REPLACE_DESTROY_FIRST) == "destroy before create"
    assert format_replace_order_label(ResourceAction.REPLACE_CREATE_FIRST) == "create before destroy"
    assert format_replace_order_label(ResourceAction.DELETE) is None


def test_resource_suffix_clauses() -> None:
    assert format_resource_suffix_clauses(
        ResourceAction.REPLACE_CREATE_FIRST,
        action_reason="replace_because_tainted",
    ) == ["tainted", "create before destroy"]
    assert format_resource_suffix_clauses(
        ResourceAction.REPLACE_DESTROY_FIRST,
        action_reason=None,
    ) == ["destroy before create"]
    assert format_resource_suffix_clauses(
        ResourceAction.DELETE,
        action_reason="delete_because_no_resource_config",
    ) == ["removed from config"]
