from __future__ import annotations

from pathlib import Path

from tfdo._internal.output.apply_outputs_renderer import (
    render_apply_outputs_ci,
    render_apply_outputs_tty,
)
from tfdo._internal.output.stream_models import ApplyOutputValue


def test_render_apply_outputs_tty_and_ci() -> None:
    entries = {
        "server_name": ApplyOutputValue(value="web-pure-elk"),
        "secret": ApplyOutputValue(value="hidden", sensitive=True),
    }
    tty = render_apply_outputs_tty(entries, terminal_width=120, spill_path=Path("/tmp/out/.tfdo/outputs.json"))
    assert tty[0] == "📤 Outputs"
    assert "  secret = (sensitive)" in tty
    assert '  server_name = "web-pure-elk"' in tty

    ci = render_apply_outputs_ci(entries)
    assert ci == [
        "outputs: secret = (sensitive)",
        'outputs: server_name = "web-pure-elk"',
    ]


def test_render_apply_outputs_ci_truncates_long_values() -> None:
    long_value = "x" * 500
    entries = {"big": ApplyOutputValue(value=long_value)}
    lines = render_apply_outputs_ci(entries, max_value_chars=20)
    assert lines[0].startswith('outputs: big = "')
    assert lines[0].endswith("...")
