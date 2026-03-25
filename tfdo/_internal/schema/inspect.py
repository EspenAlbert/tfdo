from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NamedTuple

from ask_shell.shell import ShellError, run_and_wait
from zero_3rdparty.file_utils import ensure_parents_write_text

from tfdo._internal.core import binary, executor
from tfdo._internal.models import InitInput
from tfdo._internal.schema import cache as schema_cache
from tfdo._internal.schema import terraform_cli_config as tf_cli
from tfdo._internal.settings import TfDoSettings

logger = logging.getLogger(__name__)


class FetchProvidersSchemaResult(NamedTuple):
    payload: dict
    resolved_version: str


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


def _env_registry_only() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k != tf_cli.TF_CLI_CONFIG_FILE_ENV}


def _subprocess_sees_tf_cli_config_file(env_for_tf: dict[str, str] | None) -> bool:
    if env_for_tf is not None:
        return tf_cli.TF_CLI_CONFIG_FILE_ENV in env_for_tf
    return bool(os.environ.get(tf_cli.TF_CLI_CONFIG_FILE_ENV, "").strip())


def _skip_schema_disk_cache(
    *,
    no_cache: bool,
    use_dev_overrides: bool,
    env_for_tf: dict[str, str] | None,
) -> bool:
    if no_cache:
        return True
    if use_dev_overrides:
        return _subprocess_sees_tf_cli_config_file(env_for_tf)
    return False


def _env_for_schema_fetch(
    *,
    use_dev_overrides: bool,
    workspace_root: Path,
    registry_source: str,
) -> dict[str, str] | None:
    if use_dev_overrides:
        return tf_cli.subprocess_env_for_schema_temp_dir(
            workspace_root=workspace_root,
            registry_source=registry_source,
        )
    return _env_registry_only()


def _terraform_init_or_raise(settings: TfDoSettings, env_for_tf: dict[str, str] | None) -> None:
    init_result = executor.init(InitInput(settings=settings, extra_args=["-input=false", "-no-color"], env=env_for_tf))
    if init_result.exit_code != 0:
        msg = f"terraform init failed (exit {init_result.exit_code})"
        if init_result.stderr:
            raise RuntimeError(f"{msg}\n{init_result.stderr}")
        raise RuntimeError(msg)


def _try_disk_cache_read(
    *,
    skip_disk_cache: bool,
    resolved: str,
    cache_root: Path,
    local_name: str,
    source: str,
) -> FetchProvidersSchemaResult | None:
    if skip_disk_cache:
        return None
    rel = schema_cache.cache_relative_path(
        local_name=local_name,
        source=source,
        resolved_version=resolved,
    )
    cached = schema_cache.try_read_cached_schema(cache_root / rel)
    if cached is None:
        return None
    logger.info(f"schema cache hit for {local_name} {source} {resolved}")
    return FetchProvidersSchemaResult(cached, resolved)


def _providers_schema_json_or_raise(
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


def _disk_cache_write_if_enabled(
    *,
    skip_disk_cache: bool,
    resolved: str,
    cache_root: Path,
    local_name: str,
    source: str,
    payload: dict,
) -> None:
    if skip_disk_cache:
        return
    rel = schema_cache.cache_relative_path(
        local_name=local_name,
        source=source,
        resolved_version=resolved,
    )
    schema_cache.write_cached_schema(cache_root, rel, payload)


def fetch_providers_schema_json(
    settings: TfDoSettings,
    *,
    local_name: str,
    source: str,
    version: str,
    no_cache: bool = False,
    schema_cache_root: Path | None = None,
    use_dev_overrides: bool = True,
) -> FetchProvidersSchemaResult:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        ensure_parents_write_text(
            root / "providers.tf",
            render_providers_tf(local_name=local_name, source=source, version=version),
        )
        ws = settings.model_copy(update={"work_dir": root})
        env_for_tf = _env_for_schema_fetch(
            use_dev_overrides=use_dev_overrides,
            workspace_root=root,
            registry_source=source,
        )
        skip_disk_cache = _skip_schema_disk_cache(
            no_cache=no_cache,
            use_dev_overrides=use_dev_overrides,
            env_for_tf=env_for_tf,
        )
        if _subprocess_sees_tf_cli_config_file(env_for_tf):
            logger.warning(
                "TF_CLI_CONFIG_FILE applies to this schema fetch; resolution may follow CLI config or dev_overrides"
            )
            resolved_version = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")  # dev override label
        else:
            _terraform_init_or_raise(ws, env_for_tf)  # not needed for reading schema when dev overrides apply
            resolved_version = schema_cache.read_resolved_version_from_lock(workspace_root=root, source=source)
        cache_root = schema_cache_root if schema_cache_root is not None else settings.schema_cache_dir

        if hit := _try_disk_cache_read(
            skip_disk_cache=skip_disk_cache,
            resolved=resolved_version,
            cache_root=cache_root,
            local_name=local_name,
            source=source,
        ):
            return hit

        payload = _providers_schema_json_or_raise(settings, root, env_for_tf)
        _disk_cache_write_if_enabled(
            skip_disk_cache=skip_disk_cache,
            resolved=resolved_version,
            cache_root=cache_root,
            local_name=local_name,
            source=source,
            payload=payload,
        )
        return FetchProvidersSchemaResult(payload, resolved_version)
