from __future__ import annotations

import json
import logging
from pathlib import Path

from hcl2.api import load as hcl2_load

logger = logging.getLogger(__name__)

REGISTRY_HOST_PREFIX = "registry.terraform.io/"


def lock_provider_address(source: str) -> str:
    return f"{REGISTRY_HOST_PREFIX}{source}"


def read_resolved_version_from_lock(*, workspace_root: Path, source: str) -> str | None:
    lock_path = workspace_root / ".terraform.lock.hcl"
    if not lock_path.is_file():
        return None
    addr = lock_provider_address(source)
    try:
        with lock_path.open(encoding="utf-8") as f:
            data = hcl2_load(f)
    except Exception:
        logger.warning("failed to parse .terraform.lock.hcl at %s", lock_path)
        return None
    blocks = data.get("provider")
    if not isinstance(blocks, list):
        return None
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if addr not in block:
            continue
        inner = block[addr]
        if not isinstance(inner, dict):
            return None
        raw_ver = inner.get("version")
        ver = _coerce_version_string(raw_ver)
        if ver:
            return ver
        return None
    return None


def _coerce_version_string(raw_ver: object) -> str | None:
    if isinstance(raw_ver, str) and raw_ver.strip():
        return raw_ver.strip()
    if isinstance(raw_ver, list) and len(raw_ver) == 1 and isinstance(raw_ver[0], str) and raw_ver[0].strip():
        return raw_ver[0].strip()
    return None


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
