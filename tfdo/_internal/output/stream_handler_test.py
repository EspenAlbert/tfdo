from __future__ import annotations

import json
from unittest.mock import patch

from tfdo._internal.output.stream_handler import PlanStreamHandler


def _line(payload: dict) -> str:
    return json.dumps(payload) + "\n"


def test_fast_plan_no_heartbeats() -> None:
    handler = PlanStreamHandler()
    with patch("tfdo._internal.output.stream_handler.ask_console.print_to_live") as print_mock:
        handler.feed_line(_line({"type": "refresh_complete", "hook": {"resource": {"addr": "a"}}}))
        handler.feed_line(_line({"type": "change_summary", "changes": {"add": 0}}))
    assert not any("refresh:" in str(c) for c in print_mock.call_args_list)


def test_diagnostic_immediate() -> None:
    handler = PlanStreamHandler()
    with patch("tfdo._internal.output.stream_handler.ask_console.print_to_live") as print_mock:
        handler.feed_line(
            _line(
                {
                    "type": "diagnostic",
                    "diagnostic": {"severity": "error", "summary": "bad config", "detail": "line 1"},
                }
            )
        )
    assert print_mock.call_args[0][0] == "bad config\nline 1"


def test_slow_refresh_heartbeat_and_planning() -> None:
    handler = PlanStreamHandler()
    handler._started -= 3.0
    with patch("tfdo._internal.output.stream_handler.ask_console.print_to_live") as print_mock:
        handler.feed_line(_line({"type": "refresh_start", "hook": {"resource": {"addr": "a"}}}))
        handler._last_heartbeat -= 6.0
        handler._maybe_heartbeat()
        handler.feed_line(_line({"type": "refresh_complete", "hook": {"resource": {"addr": "a"}}}))
    lines = [c[0][0] for c in print_mock.call_args_list]
    assert any("complete" in line and "in progress" in line for line in lines)
    assert "plan: computing changes…" in lines
