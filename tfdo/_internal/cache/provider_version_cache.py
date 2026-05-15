from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from zero_3rdparty.file_utils import ensure_parents_write_text

from tfdo._internal.config.config_model import ProviderConstraint
from tfdo._internal.core import executor
from tfdo._internal.hcl_read import LOCK_FILENAME, REGISTRY_HOST_PREFIX, parse_lock_file_versions
from tfdo._internal.models import InitInput
from tfdo._internal.settings import TfDoSettings

logger = logging.getLogger(__name__)

_EXACT_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _is_exact_version(constraint: str) -> bool:
    return bool(_EXACT_VERSION_RE.match(constraint))


def _provider_cache_key(provider: ProviderConstraint) -> str:
    raw = f"{provider.name}:{provider.source or ''}:{provider.constraint or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _cache_dir(settings: TfDoSettings, provider_key: str) -> Path:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    return settings.cache_root / "provider_versions" / today / provider_key


def _default_source(provider: ProviderConstraint) -> str:
    return provider.source or f"hashicorp/{provider.name}"


def _versions_tf_stub(provider: ProviderConstraint) -> str:
    source = _default_source(provider)
    if provider.constraint:
        inner = f'    {provider.name} = {{ source = "{source}", version = "{provider.constraint}" }}'
    else:
        inner = f'    {provider.name} = {{ source = "{source}" }}'
    return f"terraform {{\n  required_providers {{\n{inner}\n  }}\n}}\n"


def _resolve_single(provider: ProviderConstraint, settings: TfDoSettings) -> str | None:
    """Resolve a single provider's version via a per-provider cache directory."""
    key = _provider_cache_key(provider)
    cache = _cache_dir(settings, key)
    lock_path = cache / LOCK_FILENAME

    if not lock_path.is_file():
        cache.mkdir(parents=True, exist_ok=True)
        ensure_parents_write_text(cache / "versions.tf", _versions_tf_stub(provider))
        try:
            result = executor.init(InitInput(settings=settings.with_work_dir(cache)))
            if result.exit_code != 0:
                logger.warning(f"terraform init failed for provider {provider.name}: {result.stderr}")
                return None
        except Exception:
            logger.warning(f"terraform init failed for provider {provider.name}", exc_info=True)
            return None

    if not lock_path.is_file():
        return None

    source = _default_source(provider)
    addr = f"{REGISTRY_HOST_PREFIX}{source}"
    lock_versions = parse_lock_file_versions(lock_path)
    return lock_versions.get(addr)


def resolve_provider_versions(providers: list[ProviderConstraint], settings: TfDoSettings) -> list[ProviderConstraint]:
    to_resolve = [p for p in providers if not (p.constraint and _is_exact_version(p.constraint))]
    if not to_resolve:
        return providers

    resolved_map: dict[str, str] = {}
    for p in to_resolve:
        if version := _resolve_single(p, settings):
            resolved_map[p.name] = version

    return [
        ProviderConstraint(name=p.name, source=p.source, constraint=resolved_map.get(p.name, p.constraint))
        for p in providers
    ]
