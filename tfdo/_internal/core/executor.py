import json
import logging

from ask_shell._internal.models import EmptyOutputError
from ask_shell.shell import ShellError, run_and_wait

from tfdo._internal.core import apply_logic, binary, destroy_logic, plan_logic
from tfdo._internal.models import (
    ApplyInput,
    ApplyResult,
    DestroyInput,
    DestroyResult,
    OutputInput,
    OutputResult,
    PlanInput,
    PlanResult,
)

logger = logging.getLogger(__name__)


def plan(input_model: PlanInput) -> PlanResult:
    return plan_logic.run_plan(input_model)


def apply(input_model: ApplyInput) -> ApplyResult:
    return apply_logic.run_apply(input_model)


def destroy(input_model: DestroyInput) -> DestroyResult:
    return destroy_logic.run_destroy(input_model)


def _parse_tf_outputs(raw: dict) -> dict[str, object]:
    return {k: v["value"] for k, v in raw.items() if isinstance(v, dict) and "value" in v}


def _build_output_command(bin_name: str, input_model: OutputInput) -> str:
    parts = [bin_name, "output", "-json"]
    if input_model.state:
        parts.append(f"-state={input_model.state}")
    if input_model.name:
        parts.append(input_model.name)
    return " ".join(parts)


def output_json(input_model: OutputInput) -> OutputResult:
    settings = input_model.settings
    cmd = _build_output_command(binary.resolve_binary(settings), input_model)
    try:
        run = run_and_wait(
            cmd,
            cwd=settings.work_dir,
            allow_non_zero_exit=True,
            ansi_content=False,
            skip_binary_check=True,
        )
        if run.exit_code and run.exit_code != 0:
            return OutputResult(exit_code=run.exit_code, stderr=run.stderr or None)
        raw = run.parse_output(dict, output_format="json")
        return OutputResult(exit_code=0, outputs=_parse_tf_outputs(raw))
    except ShellError as e:
        return OutputResult(exit_code=e.exit_code or 1, stderr=e.stderr or None)
    except EmptyOutputError:
        return OutputResult(exit_code=0, outputs={})
    except json.JSONDecodeError as e:
        return OutputResult(exit_code=1, stderr=f"failed to parse output JSON: {e}")
