from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from tfdo._internal.core import tf_files
from tfdo._internal.run.discovery import has_backend_block

logger = logging.getLogger(__name__)

COMMON_ENV_NAMES = frozenset({"dev", "staging", "prod", "production", "test", "qa", "uat", "sandbox"})


class ScanResult(BaseModel):
    directories: list[str] = Field(default_factory=list)
    inferred_pattern: str | None = None


def _walk_for_backend_dirs(repo_root: Path) -> list[Path]:
    return [d for d in tf_files.find_tf_directories(repo_root) if has_backend_block(d)]


def _infer_pattern(relative_paths: list[str]) -> str | None:
    if len(relative_paths) < 2:
        return None

    split_paths = [p.split("/") for p in relative_paths]
    depths = {len(p) for p in split_paths}
    if len(depths) != 1:
        return None

    depth = depths.pop()
    segments: list[str] = []
    capture_index = 0
    for i in range(depth):
        values = {p[i] for p in split_paths}
        if len(values) == 1:
            segments.append(values.pop())
        else:
            if values & COMMON_ENV_NAMES:
                segments.append("{env}")
            elif capture_index == 0 and i == depth - 1 or capture_index > 0 or i == depth - 1:
                segments.append("{app}")
            else:
                segments.append("{env}")
            capture_index += 1

    return "/".join(segments)


def scan_for_run_dirs(repo_root: Path) -> ScanResult:
    backend_dirs = _walk_for_backend_dirs(repo_root)
    if not backend_dirs:
        return ScanResult()
    relatives = [str(d.relative_to(repo_root)) for d in backend_dirs]
    pattern = _infer_pattern(relatives)
    return ScanResult(directories=relatives, inferred_pattern=pattern)
