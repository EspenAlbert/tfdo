from __future__ import annotations

from pathlib import Path

from ask_shell.shell import ShellError, run_and_wait

from tfdo._internal.core import binary, lifecycle_init_retry
from tfdo._internal.models import LifecycleInput, LifecycleResult
from tfdo._internal.settings import TfDoSettings


def build_lifecycle_command(binary: str, subcommand: str, var_file: Path | None, extra_flags: list[str]) -> str:
    parts = [binary, subcommand]
    if var_file:
        parts.append(f"-var-file={var_file}")
    parts.extend(extra_flags)
    return " ".join(parts)


def run_lifecycle_command[T: LifecycleResult](
    settings: TfDoSettings, cmd: str, result_cls: type[T], *, user_input: bool | None = None
) -> T:
    resolved_input = settings.is_interactive if user_input is None else user_input
    try:
        run = run_and_wait(
            cmd,
            cwd=settings.work_dir,
            allow_non_zero_exit=True,
            ansi_content=True,
            skip_binary_check=True,
            user_input=resolved_input,
        )
        return result_cls(exit_code=run.exit_code or 0, stdout=run.stdout, stderr=run.stderr or None)
    except ShellError as e:
        return result_cls(exit_code=e.exit_code or 1, stderr=e.stderr or None)


def run_lifecycle[T: LifecycleResult](
    input_model: LifecycleInput, subcommand: str, extra_flags: list[str], result_cls: type[T]
) -> T:
    settings = input_model.settings
    all_flags = [*extra_flags, *input_model.extra_args]
    cmd = build_lifecycle_command(binary.resolve_binary(settings), subcommand, input_model.var_file, all_flags)

    def run_once() -> T:
        return run_lifecycle_command(settings, cmd, result_cls)

    return lifecycle_init_retry.run_with_init_retry(input_model, subcommand, result_cls, run_once)
