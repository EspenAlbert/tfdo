from __future__ import annotations

from pathlib import Path

from ask_shell.shell import ShellError, run_and_wait

from tfdo._internal.models import LifecycleResult
from tfdo._internal.settings import TfDoSettings


def build_lifecycle_command(binary: str, subcommand: str, var_file: Path | None, extra_flags: list[str]) -> str:
    parts = [binary, subcommand]
    if var_file:
        parts.append(f"-var-file={var_file}")
    parts.extend(extra_flags)
    return " ".join(parts)


def run_lifecycle_command[T: LifecycleResult](settings: TfDoSettings, cmd: str, result_cls: type[T]) -> T:
    try:
        run = run_and_wait(
            cmd,
            cwd=settings.work_dir,
            allow_non_zero_exit=True,
            ansi_content=True,
            skip_binary_check=True,
            user_input=settings.is_interactive,
        )
        return result_cls(exit_code=run.exit_code or 0, stdout=run.stdout, stderr=run.stderr or None)
    except ShellError as e:
        return result_cls(exit_code=e.exit_code or 1, stderr=e.stderr or None)
