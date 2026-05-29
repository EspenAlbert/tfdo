from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from ask_shell.shell import ShellError, run_and_wait

from tfdo._internal.config.config_file import resolve_run_context_label
from tfdo._internal.core import binary, lifecycle_env
from tfdo._internal.core.lifecycle_init_retry import run_with_init_retry
from tfdo._internal.core.lifecycle_shell import build_lifecycle_command
from tfdo._internal.models import ApplyInput, ApplyResult, DestroyInput, DestroyResult
from tfdo._internal.output.apply_blockers import build_apply_blockers
from tfdo._internal.output.apply_display import ApplyDisplayOptions, resolve_apply_display
from tfdo._internal.output.apply_state import ApplyProgressState
from tfdo._internal.output.apply_stream_handler import ApplyStreamHandler, apply_stream_callback
from tfdo._internal.output.parser import parse_plan_file
from tfdo._internal.output.plan_artifacts import plan_json_path
from tfdo._internal.settings import TfDoSettings, load_user_config

T = TypeVar("T", ApplyResult, DestroyResult)


def build_apply_stream_state(
    settings: TfDoSettings,
    plan_path: Path,
    display: ApplyDisplayOptions,
) -> ApplyProgressState:
    plan = parse_plan_file(plan_path, settings=settings)
    blockers = build_apply_blockers(plan_path)
    return ApplyProgressState(
        plan,
        blockers,
        hide_provision_output=display.hide_provision_output,
        settings=settings,
    )


def _run_streaming_apply_command(
    settings: TfDoSettings,
    cmd: str,
    handler: ApplyStreamHandler,
    *,
    print_prefix: str,
) -> ApplyResult:
    callback = apply_stream_callback(handler)
    try:
        run = run_and_wait(
            cmd,
            cwd=settings.work_dir,
            env=lifecycle_env.lifecycle_env(settings.work_dir),
            allow_non_zero_exit=True,
            ansi_content=True,
            skip_binary_check=True,
            skip_progress_output=True,
            user_input=False,
            print_prefix=print_prefix,
            message_callbacks=[callback],
        )
        handler.flush()
        return ApplyResult(
            exit_code=run.exit_code or 0,
            stderr=run.stderr or None,
            diagnostics_emitted=handler.diagnostics_emitted,
        )
    except ShellError as e:
        handler.flush()
        return ApplyResult(
            exit_code=e.exit_code or 1,
            stderr=e.stderr or None,
            diagnostics_emitted=handler.diagnostics_emitted,
        )


def run_streaming_apply(
    input_model: ApplyInput | DestroyInput,
    plan_bin: Path,
    *,
    result_cls: type[T],
) -> T:
    settings = input_model.settings
    user_config = load_user_config(settings)
    display = resolve_apply_display(ApplyDisplayOptions(), user_config.apply_display, input_model.apply_display_cli)
    plan_path = plan_json_path(settings.work_dir)
    state = build_apply_stream_state(settings, plan_path, display.options)

    extra_flags = ["-json", "-auto-approve", str(plan_bin), *input_model.extra_args]
    cmd = build_lifecycle_command(binary.resolve_binary(settings), "apply", input_model.var_file, extra_flags)
    label = resolve_run_context_label(settings.work_dir)
    print_prefix = f"{label} apply"

    def run_once() -> T:
        handler = ApplyStreamHandler(state, display, interactive=settings.is_interactive)
        result = _run_streaming_apply_command(
            settings,
            cmd,
            handler,
            print_prefix=print_prefix,
        )
        return result_cls(
            exit_code=result.exit_code,
            stderr=result.stderr,
            diagnostics_emitted=result.diagnostics_emitted,
        )

    return run_with_init_retry(input_model, "apply", result_cls, run_once)
