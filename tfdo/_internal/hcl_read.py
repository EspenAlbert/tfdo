"""Read-only HCL parsing with v7-compatible output (stripped quotes, no block markers).

Use for extracting information from .tf files. Never write results back as HCL.
For modifying .tf content, use hcl_roundtrip instead.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TextIO

from hcl2.api import load as _hcl2_load
from hcl2.api import loads as _hcl2_loads
from hcl2.utils import SerializationOptions
from zero_3rdparty.file_utils import find_repo_root

_V7_COMPAT = SerializationOptions(
    strip_string_quotes=True,
    explicit_blocks=False,
    with_comments=False,
)

REGISTRY_HOST_PREFIX = "registry.terraform.io/"
LOCK_FILENAME = ".terraform.lock.hcl"


def find_lock_file(start: Path) -> Path | None:
    """Return the nearest ``.terraform.lock.hcl`` at or above ``start``."""
    current = start.resolve()
    try:
        repo_root = find_repo_root(current)
    except ValueError:
        repo_root = None
    while True:
        candidate = current / LOCK_FILENAME
        if candidate.is_file():
            return candidate
        if repo_root is not None and current == repo_root:
            return None
        parent = current.parent
        if parent == current:
            return None
        current = parent


def hcl2_load(fp: TextIO) -> dict[str, Any]:
    return _hcl2_load(fp, serialization_options=_V7_COMPAT)


def hcl2_loads(text: str) -> dict[str, Any]:
    return _hcl2_loads(text, serialization_options=_V7_COMPAT)


def _coerce_version(raw: object) -> str | None:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, list) and len(raw) == 1 and isinstance(raw[0], str) and raw[0].strip():
        return raw[0].strip()
    return None


def parse_lock_file_versions(lock_path: Path) -> dict[str, str]:
    """Parse .terraform.lock.hcl and return {full_registry_address: version}.

    Keys are like ``registry.terraform.io/hashicorp/aws``.
    Uses v7-compat parsing so string values come back without wrapping quotes.
    """
    with lock_path.open() as f:
        data = hcl2_load(f)
    result: dict[str, str] = {}
    for block in data.get("provider", []):
        if not isinstance(block, dict):
            continue
        for registry_path, attrs in block.items():
            if not isinstance(attrs, dict):
                continue
            if version := _coerce_version(attrs.get("version")):
                result[registry_path] = version
    return result


def lock_provider_version(lock_path: Path, source: str) -> str:
    """Read the resolved version for a single provider from a lock file.

    ``source`` is the short form (e.g. ``hashicorp/aws``).
    Raises ValueError when the file is unparseable or the provider/version is missing.
    """
    addr = f"{REGISTRY_HOST_PREFIX}{source}"
    try:
        versions = parse_lock_file_versions(lock_path)
    except Exception as e:
        raise ValueError(f"failed to parse {lock_path}") from e
    if addr not in versions:
        raise ValueError(f"provider {addr!r} not found in {lock_path}")
    return versions[addr]
