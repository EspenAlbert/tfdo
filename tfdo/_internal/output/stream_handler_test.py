from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from tfdo._internal.output.stream_handler import PlanStreamHandler

_MODULE = PlanStreamHandler.__module__


def _line(payload: dict) -> str:
    return json.dumps(payload) + "\n"


@patch(f"{_MODULE}.ask_console.add_renderable")
def test_panel_removed_on_flush_only(add_mock: MagicMock) -> None:
    remove_mock = MagicMock()
    add_mock.return_value = remove_mock
    handler = PlanStreamHandler()
    handler.feed_line(_line({"type": "change_summary", "changes": {"add": 0}}))
    remove_mock.assert_not_called()
    handler.flush()
    remove_mock.assert_called_once()


@patch(f"{_MODULE}.ask_console.add_renderable", return_value=MagicMock())
def test_fast_plan_no_refresh_in_scrollback(_add_mock: MagicMock) -> None:
    handler = PlanStreamHandler()
    with patch(f"{_MODULE}.ask_console.print_to_live") as print_mock:
        handler.feed_line(_line({"type": "refresh_complete", "hook": {"resource": {"addr": "a"}}}))
        handler.feed_line(_line({"type": "change_summary", "changes": {"add": 0}}))
    assert not any("refresh" in str(c) for c in print_mock.call_args_list)
    assert handler._status_line() is None


@patch(f"{_MODULE}.ask_console.add_renderable", return_value=MagicMock())
def test_diagnostic_immediate(_add_mock: MagicMock) -> None:
    handler = PlanStreamHandler()
    with patch(f"{_MODULE}.ask_console.print_to_live") as print_mock:
        handler.feed_line(
            _line(
                {
                    "type": "diagnostic",
                    "diagnostic": {"severity": "error", "summary": "bad config", "detail": "line 1"},
                }
            )
        )
    rendered = [str(c[0][0]) for c in print_mock.call_args_list]
    assert rendered[0] == ""
    assert "Error:" in rendered[1]
    assert "bad config" in rendered[1]
    assert "line 1" in rendered[2]


@patch(f"{_MODULE}.ask_console.add_renderable", return_value=MagicMock())
def test_apply_events_and_planning_status(_add_mock: MagicMock) -> None:
    handler = PlanStreamHandler()
    with patch(f"{_MODULE}.ask_console.print_to_live") as print_mock:
        handler.feed_line(_line({"type": "apply_start", "hook": {"resource": {"addr": "a"}}}))
        status = handler._status_line()
        handler.feed_line(_line({"type": "apply_complete", "hook": {"resource": {"addr": "a"}}}))
    assert status is not None
    plain = status.plain
    assert "refresh" in plain
    assert "0 done" in plain
    assert "1 running" in plain
    assert handler._status_line().plain == "planning…"
    assert "plan: computing changes…" in [c[0][0] for c in print_mock.call_args_list]
