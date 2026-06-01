from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import uuid4

from tfdo._internal.hcl_read import LOCK_FILENAME, REGISTRY_HOST_PREFIX, find_lock_file, lock_provider_version

logger = logging.getLogger(__name__)


def lock_provider_address(source: str) -> str:
    return f"{REGISTRY_HOST_PREFIX}{source}"


def read_resolved_version_from_lock(*, workspace_root: Path, source: str) -> str:
    lock_path = find_lock_file(workspace_root)
    if lock_path is None:
        raise ValueError(f"{LOCK_FILENAME} missing at or above {workspace_root}")
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


def find_schema_cache_files(schema_cache_dir: Path, source: str, version: str) -> list[Path]:
    parts = [p for p in source.split("/") if p]
    suffix = Path(*parts) / f"{version}.json"
    suffix_len = len(suffix.parts)
    return sorted(
        p
        for p in schema_cache_dir.rglob(f"{version}.json")
        if len(p.relative_to(schema_cache_dir).parts) >= suffix_len
        and Path(*p.relative_to(schema_cache_dir).parts[-suffix_len:]) == suffix
    )


def schema_cache_hit(schema_cache_dir: Path, source: str, version: str) -> bool:
    matches = find_schema_cache_files(schema_cache_dir, source, version)
    if not matches:
        return False
    return try_read_cached_schema(matches[0]) is not None


def write_cached_schema(cache_root: Path, relative_path: Path, payload: dict) -> None:
    dest = cache_root / relative_path
    if try_read_cached_schema(dest) is not None:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    tmp = dest.parent / f".{dest.name}.{uuid4().hex}.tmp"
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(dest)
    except OSError:
        if try_read_cached_schema(dest) is not None:
            return
        raise
    finally:
        tmp.unlink(missing_ok=True)
