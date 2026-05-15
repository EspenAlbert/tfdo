from __future__ import annotations

import json
import logging
from pathlib import Path

from tfdo._internal.hcl_read import LOCK_FILENAME, REGISTRY_HOST_PREFIX, lock_provider_version

logger = logging.getLogger(__name__)


def lock_provider_address(source: str) -> str:
    return f"{REGISTRY_HOST_PREFIX}{source}"


def read_resolved_version_from_lock(*, workspace_root: Path, source: str) -> str:
    lock_path = workspace_root / LOCK_FILENAME
    if not lock_path.is_file():
        raise ValueError(f"{LOCK_FILENAME} missing under {workspace_root}")
    return lock_provider_version(lock_path, source)


def cache_relative_path(*, local_name: str, source: str, resolved_version: str) -> Path:
    segments = [p for p in source.split("/") if p]
    return Path(local_name, *segments, f"{resolved_version}.json")


def try_read_cached_schema(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("ignoring corrupt schema cache at %s", path)
        return None
    if not isinstance(obj, dict):
        logger.warning("ignoring non-object schema cache at %s", path)
        return None
    return obj


def write_cached_schema(cache_root: Path, relative_path: Path, payload: dict) -> None:
    dest = cache_root / relative_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    tmp = dest.with_suffix(f"{dest.suffix}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(dest)
