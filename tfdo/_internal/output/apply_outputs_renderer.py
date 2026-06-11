from __future__ import annotations

from pathlib import Path

from ask_shell import console as ask_console

from tfdo._internal.core import executor
from tfdo._internal.models import OutputInput
from tfdo._internal.output import output_value_format
from tfdo._internal.output.apply_state import ApplyProgressState
from tfdo._internal.output.plan_artifacts import outputs_json_path, write_outputs_json
from tfdo._internal.output.render_thresholds import OUTPUT_MULTILINE_CHARS, OUTPUT_WRAP_WIDTH
from tfdo._internal.output.stream_models import ApplyOutputValue, coerce_output_type
from tfdo._internal.settings import TfDoSettings

APPLY_OUTPUT_HEADER = "📤 Outputs"
CI_OUTPUT_PREFIX = "outputs:"
CI_MAX_VALUE_CHARS = 400
APPLY_OUTPUT_INDENT = 2


def parse_tf_output_entries(raw: dict[str, object]) -> dict[str, ApplyOutputValue]:
    entries: dict[str, ApplyOutputValue] = {}
    for name, payload in raw.items():
        if not isinstance(payload, dict) or "value" not in payload:
            continue
        entries[name] = ApplyOutputValue(
            sensitive=bool(payload.get("sensitive")),
            type=coerce_output_type(payload.get("type")),
            value=payload.get("value"),
        )
    return entries


def values_from_entries(entries: dict[str, ApplyOutputValue]) -> dict[str, object]:
    return {name: entry.value for name, entry in sorted(entries.items()) if entry.value is not None}


def _format_apply_value(entry: ApplyOutputValue) -> str:
    if entry.sensitive:
        return output_value_format.SENSITIVE
    return output_value_format.format_scalar(entry.value)


def _wrap_apply_output_lines(name: str, value_s: str, *, terminal_width: int) -> list[str]:
    pad = " " * APPLY_OUTPUT_INDENT
    value_pad = " " * (APPLY_OUTPUT_INDENT + 2)
    head = f"{name} = "
    wrap_width = min(terminal_width, OUTPUT_WRAP_WIDTH)
    if len(pad) + len(head) + len(value_s) <= wrap_width and "\n" not in value_s:
        return [f"{pad}{head}{value_s}"]
    lines = [f"{pad}{head}"]
    for value_line in value_s.splitlines():
        lines.append(f"{value_pad}{value_line}")
    return lines


def _tty_value_text(entry: ApplyOutputValue, *, spill_path: Path | None) -> str:
    if entry.sensitive:
        return output_value_format.SENSITIVE
    value_s = output_value_format.format_scalar(entry.value)
    if len(value_s) <= OUTPUT_MULTILINE_CHARS:
        return value_s
    if spill_path is not None:
        return f"(see {spill_path})"
    return value_s


def render_apply_outputs_tty(
    entries: dict[str, ApplyOutputValue],
    *,
    terminal_width: int,
    spill_path: Path | None = None,
) -> list[str]:
    if not entries:
        return []
    lines = [APPLY_OUTPUT_HEADER]
    for name in sorted(entries):
        value_s = _tty_value_text(entries[name], spill_path=spill_path)
        lines.extend(_wrap_apply_output_lines(name, value_s, terminal_width=terminal_width))
    return lines


def render_apply_outputs_ci(
    entries: dict[str, ApplyOutputValue],
    *,
    max_value_chars: int = CI_MAX_VALUE_CHARS,
) -> list[str]:
    if not entries:
        return []
    lines: list[str] = []
    for name in sorted(entries):
        value_s = _format_apply_value(entries[name])
        if len(value_s) > max_value_chars:
            value_s = f"{value_s[: max_value_chars - 3]}..."
        lines.append(f"{CI_OUTPUT_PREFIX} {name} = {value_s}")
    return lines


def load_output_entries(settings: TfDoSettings) -> dict[str, ApplyOutputValue] | None:
    result = executor.output_json(OutputInput(settings=settings))
    if result.exit_code != 0 or not result.raw_outputs:
        return None
    entries = parse_tf_output_entries(result.raw_outputs)
    return entries or None


def resolve_output_entries(
    settings: TfDoSettings,
    state: ApplyProgressState | None = None,
) -> dict[str, ApplyOutputValue] | None:
    if state is not None and state.post_apply_outputs:
        entries = {name: entry for name, entry in state.post_apply_outputs.items() if entry.value is not None}
        if entries:
            return entries
    if state is not None and state.post_apply_outputs_received:
        return None
    return load_output_entries(settings)


def emit_apply_outputs(
    settings: TfDoSettings,
    *,
    interactive: bool,
    exit_code: int,
    state: ApplyProgressState | None = None,
) -> None:
    if exit_code != 0:
        return
    entries = resolve_output_entries(settings, state)
    if not entries:
        return
    write_outputs_json(settings.work_dir, values_from_entries(entries))
    spill_path = outputs_json_path(settings.work_dir)
    if interactive:
        terminal_width = ask_console.get_live_console().size.width or 120
        lines = render_apply_outputs_tty(entries, terminal_width=terminal_width, spill_path=spill_path)
    else:
        lines = render_apply_outputs_ci(entries)
    if not lines:
        return
    ask_console.print_to_live("")
    for line in lines:
        ask_console.print_to_live(line)
