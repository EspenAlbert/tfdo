from __future__ import annotations

import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from ask_shell.shell import ShellError, run_and_wait
from zero_3rdparty.file_utils import ensure_parents_write_text

from tfdo._internal.core import binary, executor
from tfdo._internal.models import InitInput
from tfdo._internal.schema import cache as schema_cache
from tfdo._internal.schema import terraform_cli_config as tf_cli
from tfdo._internal.settings import TfDoSettings

logger = logging.getLogger(__name__)


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
    no_cache: bool = False,
    schema_cache_root: Path | None = None,
) -> dict:
    skip_disk_cache = no_cache or bool(os.environ.get(tf_cli.TF_CLI_CONFIG_FILE_ENV, "").strip())

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        ensure_parents_write_text(
            root / "providers.tf",
            render_providers_tf(local_name=local_name, source=source, version=version),
        )
        ws = settings.model_copy(update={"work_dir": root})
        env_for_tf = tf_cli.subprocess_env_for_schema_temp_dir(workspace_root=root, registry_source=source)

        init_result = executor.init(InitInput(settings=ws, extra_args=["-input=false", "-no-color"], env=env_for_tf))
        if init_result.exit_code != 0:
            msg = f"terraform init failed (exit {init_result.exit_code})"
            raise RuntimeError(msg)

        resolved = schema_cache.read_resolved_version_from_lock(workspace_root=root, source=source)
        if resolved is None:
            logger.warning(
                "could not determine resolved provider version from lock file; schema cache disabled for this run"
            )

        cache_root = schema_cache_root if schema_cache_root is not None else settings.schema_cache_dir
        rel: Path | None = None
        if not skip_disk_cache and resolved is not None:
            rel = schema_cache.cache_relative_path(
                local_name=local_name,
                source=source,
                resolved_version=resolved,
            )
            cached = schema_cache.try_read_cached_schema(cache_root / rel)
            if cached is not None:
                logger.info(f"schema cache hit for {local_name} {source} {resolved}")
                return cached

        cmd = f"{binary.resolve_binary(settings)} providers schema -json"
        try:
            run = run_and_wait(
                cmd,
                cwd=root,
                env=env_for_tf,
                ansi_content=False,
                allow_non_zero_exit=True,
                skip_binary_check=True,
            )
        except ShellError as e:
            raise RuntimeError(f"terraform providers schema failed: {e.stderr[:800]}") from e
        if run.exit_code != 0:
            raise RuntimeError(f"terraform providers schema failed (exit {run.exit_code}): {run.stderr[:800]}")
        payload = run.parse_output(dict, output_format="json")

        if not skip_disk_cache and resolved is not None and rel is not None:
            schema_cache.write_cached_schema(cache_root, rel, payload)

        return payload
