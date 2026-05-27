"""Best-effort schema cache warm during plan rendering.

When required context is still missing after warm, check:
1. ``settings.work_dir`` is the run dir where init ran.
2. ``find_lock_file(work_dir)`` returns a file listing the provider at the expected version.
3. Cache path ``{schema_cache_dir}/{local_name}/{source}/{version}.json`` exists and parses.
4. Plan ``provider_name`` matches the lock registry address (not a short local name).
5. Warm was skipped due to dev overrides, subprocess failure, or unparsed lock (see warning logs).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import NamedTuple

from tfdo._internal.hcl_read import REGISTRY_HOST_PREFIX, parse_lock_file_versions
from tfdo._internal.output.models import PlanOutput
from tfdo._internal.schema import cache as schema_cache
from tfdo._internal.schema import inspect as schema_inspect
from tfdo._internal.schema.inspect_logic import pick_provider_key
from tfdo._internal.schema.providers_schema import providers_schema_json_or_raise
from tfdo._internal.settings import TfDoSettings

logger = logging.getLogger(__name__)


class ProviderCacheMiss(NamedTuple):
    provider_addr: str
    source: str
    version: str
    local_name: str


def providers_in_plan(plan: PlanOutput) -> frozenset[str]:
    names: set[str] = set()
    for change in [*plan.resource_changes, *plan.resource_drift]:
        if change.provider_name:
            names.add(change.provider_name)
    return frozenset(names)


def cache_misses_for_providers(
    *,
    lock_versions: dict[str, str],
    providers: frozenset[str],
    schema_cache_dir: Path,
) -> list[ProviderCacheMiss]:
    misses: list[ProviderCacheMiss] = []
    for provider_addr in sorted(providers):
        if not provider_addr.startswith(REGISTRY_HOST_PREFIX):
            continue
        version = lock_versions.get(provider_addr)
        if version is None:
            continue
        source = provider_addr.removeprefix(REGISTRY_HOST_PREFIX)
        if schema_cache.schema_cache_hit(schema_cache_dir, source, version):
            continue
        local_name = source.rpartition("/")[2]
        misses.append(
            ProviderCacheMiss(
                provider_addr=provider_addr,
                source=source,
                version=version,
                local_name=local_name,
            )
        )
    return misses


def write_provider_schema_caches(
    *,
    payload: dict,
    misses: list[ProviderCacheMiss],
    schema_cache_dir: Path,
) -> None:
    pschemas = payload.get("provider_schemas")
    if not isinstance(pschemas, dict):
        logger.warning("providers schema response missing provider_schemas; skipping cache write")
        return
    format_version = payload.get("format_version", "1.0")
    for miss in misses:
        try:
            pkey = pick_provider_key(pschemas, local_name=miss.local_name, source=miss.source)
        except ValueError as e:
            logger.warning(f"schema cache write skipped for {miss.source}: {e}")
            continue
        entry = pschemas.get(pkey)
        if not isinstance(entry, dict):
            logger.warning(f"schema cache write skipped for {miss.source}: provider entry missing")
            continue
        single_payload = {
            "format_version": format_version,
            "provider_schemas": {pkey: entry},
        }
        rel = schema_cache.cache_relative_path(
            local_name=miss.local_name,
            source=miss.source,
            resolved_version=miss.version,
        )
        schema_cache.write_cached_schema(schema_cache_dir, rel, single_payload)
        logger.info(f"schema cache warmed for {miss.local_name} {miss.source} {miss.version}")


def warm_plan_schema_cache(
    settings: TfDoSettings,
    *,
    lock_path: Path,
    plan: PlanOutput,
    schema_cache_dir: Path,
) -> None:
    try:
        lock_versions = parse_lock_file_versions(lock_path)
    except (OSError, ValueError) as e:
        logger.warning(f"failed to parse lock file {lock_path}: {e}")
        return

    plan_providers = providers_in_plan(plan)
    misses = cache_misses_for_providers(
        lock_versions=lock_versions,
        providers=plan_providers,
        schema_cache_dir=schema_cache_dir,
    )
    if not misses:
        return

    env_for_tf = schema_inspect._env_registry_only()
    skip_disk_cache = schema_inspect._skip_schema_disk_cache(
        no_cache=False,
        use_dev_overrides=True,
        env_for_tf=env_for_tf,
    )
    if skip_disk_cache:
        logger.warning(
            "schema cache warm skipped: TF_CLI_CONFIG_FILE dev overrides apply; "
            "run tfdo schema show to populate cache for registry providers"
        )
        return

    try:
        payload = providers_schema_json_or_raise(settings, settings.work_dir, env_for_tf)
    except RuntimeError as e:
        logger.warning(f"schema cache warm failed: {e}")
        return

    write_provider_schema_caches(payload=payload, misses=misses, schema_cache_dir=schema_cache_dir)
