from __future__ import annotations

from ask_shell import console as ask_console

from tfdo._internal.core import binary
from tfdo._internal.output.plan_artifacts import plan_bin_path, plan_json_path
from tfdo._internal.output.plan_display import DetailLevel
from tfdo._internal.settings import TfDoSettings


def print_plan_footer(settings: TfDoSettings, *, detail: DetailLevel) -> None:
    if settings.passthrough:
        return
    bin_path = plan_bin_path(settings.work_dir).resolve()
    json_path = plan_json_path(settings.work_dir).resolve()
    binary_cmd = binary.resolve_binary(settings)
    lines = [
        f"Full plan:  {binary_cmd} show {bin_path}",
        f"Plan JSON:  {json_path}",
    ]
    if detail == DetailLevel.COMPACT:
        lines.append("More depth: tfdo plan --detail full")
    for line in lines:
        ask_console.print_to_live(line, style="dim")
