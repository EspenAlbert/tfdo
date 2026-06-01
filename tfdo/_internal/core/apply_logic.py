from __future__ import annotations

import logging
from pathlib import Path

from ask_shell import ask

from tfdo._internal.core import (
    apply_subprocess,
    failure_output,
    lifecycle_shell,
    plan_logic,
)
from tfdo._internal.core.lifecycle_footer import print_lifecycle_footer
from tfdo._internal.models import ApplyInput, ApplyResult, PlanInput
from tfdo._internal.output import apply_outputs_renderer, plan_artifacts

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
        orchestration_active=input_model.orchestration_active,
    )


def _confirm_apply() -> bool:
    return ask.confirm(APPLY_PROMPT, default=False)


def _apply_saved_plan(input_model: ApplyInput, plan_bin: Path) -> ApplyResult:
    return apply_subprocess.run_streaming_apply(input_model, plan_bin, result_cls=ApplyResult)


def run_apply(input_model: ApplyInput) -> ApplyResult:
    if input_model.settings.passthrough:
        extra_flags: list[str] = []
        if input_model.auto_approve:
            extra_flags.append("-auto-approve")
        result = lifecycle_shell.run_lifecycle(input_model, "apply", extra_flags, ApplyResult)
        if result.exit_code != 0:
            failure_output.report_lifecycle_failure(
                command="apply",
                exit_code=result.exit_code,
                stderr=result.stderr,
            )
        return result

    plan_result = plan_logic.plan_and_render(_plan_input_from_apply(input_model))
    if plan_result.exit_code != 0:
        return ApplyResult(exit_code=plan_result.exit_code, stderr=plan_result.stderr)

    if plan_result.has_applyable_changes is False:
        logger.info("plan has no applyable changes; skipping apply")
        apply_outputs_renderer.emit_apply_outputs(
            input_model.settings,
            interactive=input_model.settings.is_interactive,
            exit_code=0,
        )
        return ApplyResult(exit_code=0)

    bin_path = plan_artifacts.plan_bin_path(input_model.settings.work_dir)
    if not bin_path.is_file():
        return ApplyResult(exit_code=plan_result.exit_code, stderr=plan_result.stderr)

    if input_model.auto_approve or _confirm_apply():
        apply_result = _apply_saved_plan(input_model, bin_path)
        if apply_result.exit_code != 0:
            failure_output.report_lifecycle_failure(
                command="apply",
                exit_code=apply_result.exit_code,
                stderr=apply_result.stderr,
            )
            print_lifecycle_footer(input_model.settings, detail=input_model.detail)
        return apply_result

    logger.info("apply cancelled")
    return ApplyResult(exit_code=0)
