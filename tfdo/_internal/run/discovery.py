from __future__ import annotations

import logging
import re
from pathlib import Path

from pydantic import BaseModel, Field

from tfdo._internal.config.config_resolution import ResolvedConfig
from tfdo._internal.hcl_compat import hcl2_loads
from tfdo._internal.run.run_context import RunDirContext

logger = logging.getLogger(__name__)

_SEGMENT_RE = re.compile(r"\{(?P<name>[a-zA-Z_]\w*)\}\?|\{(?P<req_name>[a-zA-Z_]\w*)\}")


class DiscoveryPattern(BaseModel):
    raw: str
    regex: re.Pattern[str]
    selector_names: list[str]
    optional_selectors: set[str] = Field(default_factory=set)

    model_config = {"arbitrary_types_allowed": True}

    def match(self, relative_path: str) -> dict[str, str] | None:
        normalized = relative_path.rstrip("/") + "/"
        if m := self.regex.match(normalized):
            return {k: v for k, v in m.groupdict().items() if v is not None}
        return None


def parse_discovery_pattern(pattern: str) -> DiscoveryPattern:
    if not pattern.strip():
        raise ValueError("discovery pattern must not be empty")

    segments = pattern.strip("/").split("/")
    regex_parts: list[str] = []
    selector_names: list[str] = []
    optional_selectors: set[str] = set()

    for segment in segments:
        if m := _SEGMENT_RE.fullmatch(segment):
            if opt_name := m.group("name"):
                optional_selectors.add(opt_name)
                selector_names.append(opt_name)
                regex_parts.append(f"(?:(?P<{opt_name}>[^/]+)/)?")
            else:
                req_name = m.group("req_name")
                selector_names.append(req_name)
                regex_parts.append(f"(?P<{req_name}>[^/]+)/")
        else:
            regex_parts.append(re.escape(segment) + "/")

    if len(optional_selectors) > 1:
        raise ValueError(f"max one optional segment allowed, got: {sorted(optional_selectors)}")

    compiled = re.compile("^" + "".join(regex_parts) + "$")
    return DiscoveryPattern(
        raw=pattern,
        regex=compiled,
        selector_names=selector_names,
        optional_selectors=optional_selectors,
    )


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


def _iter_dirs_at_depth(root: Path, min_depth: int, max_depth: int) -> list[Path]:
    results: list[Path] = []

    def _walk(current: Path, depth: int) -> None:
        if depth > max_depth:
            return
        if depth >= min_depth:
            results.append(current)
        if depth < max_depth:
            try:
                for child in sorted(current.iterdir()):
                    if child.is_dir() and child.name != ".terraform":
                        _walk(child, depth + 1)
            except PermissionError:
                pass

    _walk(root, 0)
    return results


def discover_run_dirs(
    repo_root: Path, pattern: DiscoveryPattern, require_backend: bool = True
) -> list[DiscoveredRunDir]:
    total_segments = len(pattern.raw.strip("/").split("/"))
    optional_count = len(pattern.optional_selectors)
    min_depth = total_segments - optional_count
    max_depth = total_segments

    discovered: list[DiscoveredRunDir] = []
    for directory in _iter_dirs_at_depth(repo_root, min_depth, max_depth):
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
