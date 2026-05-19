from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

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

    def context_label(self, selectors: dict[str, str]) -> str:
        return "/".join(selectors[name] for name in self.selector_names if name in selectors)


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


def iter_dirs_at_depth(root: Path, min_depth: int, max_depth: int) -> list[Path]:
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
