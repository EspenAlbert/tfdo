from __future__ import annotations

from pathlib import Path

from ask_shell.shell import ShellError, run_and_wait

from tfdo._internal.core import binary
from tfdo._internal.settings import TfDoSettings


def providers_schema_json_or_raise(
    settings: TfDoSettings,
    workspace_root: Path,
    env_for_tf: dict[str, str] | None,
) -> dict:
    cmd = f"{binary.resolve_binary(settings)} providers schema -json"
    try:
        run = run_and_wait(
            cmd,
            cwd=workspace_root,
            env=env_for_tf,
            ansi_content=False,
            allow_non_zero_exit=True,
            skip_binary_check=True,
        )
    except ShellError as e:
        raise RuntimeError(f"terraform providers schema failed: {e.stderr[:800]}") from e
    if run.exit_code != 0:
        raise RuntimeError(f"terraform providers schema failed (exit {run.exit_code}): {run.stderr[:800]}")
    return run.parse_output(dict, output_format="json")
