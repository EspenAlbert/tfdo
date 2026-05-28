from __future__ import annotations

import json
import logging
from pathlib import Path

from ask_shell._internal.models import EmptyOutputError
from ask_shell.shell import ShellError, run_and_wait

from tfdo._internal.core import binary, lifecycle_env
from tfdo._internal.core.lifecycle_init_retry import run_with_init_retry
from tfdo._internal.core.lifecycle_shell import build_lifecycle_command
from tfdo._internal.models import PlanInput, PlanResult
from tfdo._internal.output.models import PlanOutput
from tfdo._internal.output.plan_artifacts import plan_bin_path
from tfdo._internal.output.stream_handler import PlanStreamHandler, plan_stream_callback
from tfdo._internal.settings import TfDoSettings

logger = logging.getLogger(__name__)


def _run_streaming_command(
    settings: TfDoSettings, cmd: str, handler: PlanStreamHandler, *, print_prefix: str
) -> PlanResult:
    callback = plan_stream_callback(handler)
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
        return PlanResult(
            exit_code=run.exit_code or 0,
            stderr=run.stderr or None,
            diagnostics_emitted=handler.diagnostics_emitted,
        )
    except ShellError as e:
        handler.flush()
        return PlanResult(
            exit_code=e.exit_code or 1,
            stderr=e.stderr or None,
            diagnostics_emitted=handler.diagnostics_emitted,
        )


def run_streaming_plan(input_model: PlanInput) -> PlanResult:
    settings = input_model.settings
    bin_path = plan_bin_path(settings.work_dir)
    extra_flags = ["-json", f"-out={bin_path}"]
    if input_model.destroy_plan:
        extra_flags.insert(0, "-destroy")
    all_flags = [*extra_flags, *input_model.extra_args]
    cmd = build_lifecycle_command(binary.resolve_binary(settings), "plan", input_model.var_file, all_flags)

    def run_once() -> PlanResult:
        handler = PlanStreamHandler()
        plan_label = "destroy plan" if input_model.destroy_plan else "plan"
        print_prefix = f"{input_model.run_context_label} {plan_label}"
        return _run_streaming_command(settings, cmd, handler, print_prefix=print_prefix)

    return run_with_init_retry(input_model, "plan", PlanResult, run_once)


def show_plan_json(settings: TfDoSettings, plan_bin: Path) -> tuple[PlanOutput | None, int]:
    cmd = f"{binary.resolve_binary(settings)} show -json {plan_bin}"
    try:
        run = run_and_wait(
            cmd,
            cwd=settings.work_dir,
            allow_non_zero_exit=True,
            ansi_content=False,
            skip_binary_check=True,
        )
        exit_code = run.exit_code or 0
        if exit_code != 0:
            return None, exit_code
        return run.parse_output(PlanOutput), 0
    except ShellError as e:
        return None, e.exit_code or 1
    except EmptyOutputError as e:
        logger.error(f"terraform show -json produced no stdout: {e}")
        return None, 1
    except json.JSONDecodeError as e:
        logger.error(f"failed to parse terraform show -json output: {e}")
        return None, 1
