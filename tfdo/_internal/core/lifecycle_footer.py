from __future__ import annotations

from ask_shell import console as ask_console

from tfdo._internal.core import binary, lifecycle_env
from tfdo._internal.output.plan_artifacts import plan_bin_path, plan_json_path
from tfdo._internal.output.plan_display import DetailLevel
from tfdo._internal.settings import TfDoSettings


def lifecycle_footer_lines(settings: TfDoSettings, *, detail: DetailLevel) -> list[str]:
    if settings.passthrough:
        return []
    lines: list[str] = []
    bin_path = plan_bin_path(settings.work_dir).resolve()
    json_path = plan_json_path(settings.work_dir).resolve()
    if bin_path.is_file():
        binary_cmd = binary.resolve_binary(settings)
        lines.append(f"Full plan:  {binary_cmd} show {bin_path}")
    if json_path.is_file():
        lines.append(f"Plan JSON:  {json_path}")
    lines.append(f"Debug log:  {lifecycle_env.resolved_debug_log_path(settings.work_dir)}")
    if detail == DetailLevel.COMPACT:
        lines.append("More depth: tfdo plan --detail full")
    return lines


def print_lifecycle_footer(settings: TfDoSettings, *, detail: DetailLevel) -> None:
    for line in lifecycle_footer_lines(settings, detail=detail):
        ask_console.print_to_live(line, style="dim")
