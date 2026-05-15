from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from tfdo._internal.config.config_resolution import ResolvedConfig
from tfdo._internal.config.discovery_pattern import DiscoveryPattern, iter_dirs_at_depth
from tfdo._internal.hcl_read import hcl2_loads
from tfdo._internal.run.run_context import RunDirContext

logger = logging.getLogger(__name__)


def has_backend_block(directory: Path) -> bool:
    for tf_file in directory.glob("*.tf"):
        if tf_file.is_relative_to(directory / ".terraform"):
            continue
        try:
            data = hcl2_loads(tf_file.read_text())
        except Exception:
            logger.warning(f"skipping unparseable file: {tf_file}")
            continue
        for terraform_block in data.get("terraform", []):
            if "backend" in terraform_block:
                return True
    return False


class DiscoveredRunDir(BaseModel):
    path: Path
    relative_path: str
    selectors: dict[str, str] = Field(default_factory=dict)


def discover_run_dirs(
    repo_root: Path, pattern: DiscoveryPattern, require_backend: bool = True
) -> list[DiscoveredRunDir]:
    total_segments = len(pattern.raw.strip("/").split("/"))
    optional_count = len(pattern.optional_selectors)
    min_depth = total_segments - optional_count
    max_depth = total_segments

    discovered: list[DiscoveredRunDir] = []
    for directory in iter_dirs_at_depth(repo_root, min_depth, max_depth):
        rel = str(directory.relative_to(repo_root))
        selectors = pattern.match(rel)
        if selectors is not None and (not require_backend or has_backend_block(directory)):
            discovered.append(DiscoveredRunDir(path=directory, relative_path=rel, selectors=selectors))

    return sorted(discovered, key=lambda d: d.relative_path)


def build_run_dir_contexts(
    discovered: list[DiscoveredRunDir],
    resolved_config: ResolvedConfig,
    repo_owner: str,
    repo_name: str,
) -> list[RunDirContext]:
    contexts: list[RunDirContext] = []
    for run_dir in discovered:
        tags = {**resolved_config.tags, **run_dir.selectors}
        name = run_dir.relative_path.rsplit("/", 1)[-1]
        contexts.append(
            RunDirContext(
                name=name,
                path=run_dir.relative_path,
                repo_owner=repo_owner,
                repo_name=repo_name,
                tags=tags,
            )
        )
    return contexts
