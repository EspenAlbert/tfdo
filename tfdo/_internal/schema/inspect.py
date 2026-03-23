from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from ask_shell.shell import ShellError, run_and_wait
from zero_3rdparty.file_utils import ensure_parents_write_text

from tfdo._internal.core import binary, executor
from tfdo._internal.models import InitInput
from tfdo._internal.settings import TfDoSettings


def render_providers_tf(*, local_name: str, source: str, version: str) -> str:
    return f"""terraform {{
  required_providers {{
    {local_name} = {{
      source  = "{source}"
      version = "{version}"
    }}
  }}
}}
"""


def fetch_providers_schema_json(
    settings: TfDoSettings,
    *,
    local_name: str,
    source: str,
    version: str,
) -> dict:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        ensure_parents_write_text(
            root / "providers.tf",
            render_providers_tf(local_name=local_name, source=source, version=version),
        )
        ws = settings.model_copy(update={"work_dir": root})
        init_result = executor.init(InitInput(settings=ws, extra_args=["-input=false", "-no-color"]))
        if init_result.exit_code != 0:
            msg = f"terraform init failed (exit {init_result.exit_code})"
            raise RuntimeError(msg)
        cmd = f"{binary.resolve_binary(settings)} providers schema -json"
        try:
            run = run_and_wait(
                cmd,
                cwd=root,
                ansi_content=False,
                allow_non_zero_exit=True,
                skip_binary_check=True,
            )
        except ShellError as e:
            raise RuntimeError(f"terraform providers schema failed: {e.stderr[:800]}") from e
        if run.exit_code != 0:
            raise RuntimeError(f"terraform providers schema failed (exit {run.exit_code}): {run.stderr[:800]}")
        return run.parse_output(dict, output_format="json")
