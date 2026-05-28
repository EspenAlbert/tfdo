from __future__ import annotations

import logging
from pathlib import Path

from ask_shell import ask

from tfdo._internal.core import binary, failure_output, lifecycle_init_retry, lifecycle_shell, plan_logic
from tfdo._internal.models import DestroyInput, DestroyResult, PlanInput
from tfdo._internal.output import plan_artifacts
from tfdo._internal.core.lifecycle_footer import print_lifecycle_footer

logger = logging.getLogger(__name__)

DESTROY_PROMPT = "Destroy these resources?"


def _plan_input_from_destroy(input_model: DestroyInput) -> PlanInput:
    return PlanInput(
        settings=input_model.settings,
        var_file=input_model.var_file,
        init_mode=input_model.init_mode,
        extra_args=input_model.extra_args,
        init_backend_args=input_model.init_backend_args,
        plan_display_cli=input_model.plan_display_cli,
        detail=input_model.detail,
        destroy_plan=True,
    )


def _confirm_destroy() -> bool:
    return ask.confirm(DESTROY_PROMPT, default=False)


def _apply_saved_plan(input_model: DestroyInput, plan_bin: Path) -> DestroyResult:
    settings = input_model.settings
    extra_flags = ["-auto-approve", str(plan_bin), *input_model.extra_args]
    cmd = lifecycle_shell.build_lifecycle_command(
        binary.resolve_binary(settings), "apply", input_model.var_file, extra_flags
    )

    def run_once() -> DestroyResult:
        return lifecycle_shell.run_lifecycle_command(settings, cmd, DestroyResult, user_input=False)

    return lifecycle_init_retry.run_with_init_retry(input_model, "apply", DestroyResult, run_once)


def run_destroy(input_model: DestroyInput) -> DestroyResult:
    if input_model.settings.passthrough:
        extra_flags: list[str] = []
        if input_model.auto_approve:
            extra_flags.append("-auto-approve")
        result = lifecycle_shell.run_lifecycle(input_model, "destroy", extra_flags, DestroyResult)
        if result.exit_code != 0:
            failure_output.report_lifecycle_failure(
                command="destroy",
                exit_code=result.exit_code,
                stderr=result.stderr,
            )
        return result

    plan_result = plan_logic.plan_and_render(_plan_input_from_destroy(input_model))
    if plan_result.exit_code != 0:
        return DestroyResult(exit_code=plan_result.exit_code, stderr=plan_result.stderr)

    bin_path = plan_artifacts.plan_bin_path(input_model.settings.work_dir)
    if not bin_path.is_file():
        return DestroyResult(exit_code=plan_result.exit_code, stderr=plan_result.stderr)

    if input_model.auto_approve or _confirm_destroy():
        destroy_result = _apply_saved_plan(input_model, bin_path)
        if destroy_result.exit_code != 0:
            failure_output.report_lifecycle_failure(
                command="destroy",
                exit_code=destroy_result.exit_code,
                stderr=destroy_result.stderr,
            )
            print_lifecycle_footer(input_model.settings, detail=input_model.detail)
        return destroy_result

    logger.info("destroy cancelled")
    return DestroyResult(exit_code=0)
