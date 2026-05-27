from __future__ import annotations

import logging
from pathlib import Path

from ask_shell import ask

from tfdo._internal.core import binary, lifecycle_init_retry, lifecycle_shell, plan_logic
from tfdo._internal.models import ApplyInput, ApplyResult, PlanInput
from tfdo._internal.output import plan_artifacts

logger = logging.getLogger(__name__)

APPLY_PROMPT = "Apply this plan?"


def _plan_input_from_apply(input_model: ApplyInput) -> PlanInput:
    return PlanInput(
        settings=input_model.settings,
        var_file=input_model.var_file,
        init_mode=input_model.init_mode,
        extra_args=input_model.extra_args,
        init_backend_args=input_model.init_backend_args,
        plan_display_cli=input_model.plan_display_cli,
        detail=input_model.detail,
    )


def _confirm_apply() -> bool:
    return ask.confirm(APPLY_PROMPT, default=False)


def _apply_saved_plan(input_model: ApplyInput, plan_bin: Path) -> ApplyResult:
    settings = input_model.settings
    extra_flags = ["-auto-approve", str(plan_bin), *input_model.extra_args]
    cmd = lifecycle_shell.build_lifecycle_command(
        binary.resolve_binary(settings), "apply", input_model.var_file, extra_flags
    )

    def run_once() -> ApplyResult:
        return lifecycle_shell.run_lifecycle_command(settings, cmd, ApplyResult, user_input=False)

    return lifecycle_init_retry.run_with_init_retry(input_model, "apply", ApplyResult, run_once)


def run_apply(input_model: ApplyInput) -> ApplyResult:
    if input_model.settings.passthrough:
        extra_flags: list[str] = []
        if input_model.auto_approve:
            extra_flags.append("-auto-approve")
        return lifecycle_shell.run_lifecycle(input_model, "apply", extra_flags, ApplyResult)

    plan_result = plan_logic.plan_and_render(_plan_input_from_apply(input_model))
    if plan_result.exit_code != 0:
        return ApplyResult(exit_code=plan_result.exit_code, stderr=plan_result.stderr)

    bin_path = plan_artifacts.plan_bin_path(input_model.settings.work_dir)
    if not bin_path.is_file():
        return ApplyResult(exit_code=plan_result.exit_code, stderr=plan_result.stderr)

    if input_model.auto_approve or _confirm_apply():
        return _apply_saved_plan(input_model, bin_path)

    logger.info("apply cancelled")
    return ApplyResult(exit_code=0)
