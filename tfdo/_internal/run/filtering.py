from __future__ import annotations

import logging

from pydantic import BaseModel

from tfdo._internal.run.discovery import DiscoveredRunDir

logger = logging.getLogger(__name__)


class TagFilter(BaseModel):
    key: str
    values: list[str]

    @classmethod
    def parse(cls, raw: str) -> TagFilter:
        if "=" not in raw:
            raise ValueError(f"tag filter must be 'key=value[,value2]', got: {raw!r}")
        key, values_str = raw.split("=", 1)
        return cls(key=key.strip(), values=[v.strip() for v in values_str.split(",")])

    def matches(self, tags: dict[str, str]) -> bool:
        return tags.get(self.key, "") in self.values


def filter_by_selectors(
    run_dirs: list[DiscoveredRunDir],
    selector_filters: dict[str, str],
) -> list[DiscoveredRunDir]:
    if not selector_filters:
        return run_dirs
    result: list[DiscoveredRunDir] = []
    for rd in run_dirs:
        if all(rd.selectors.get(key, "") in value.split(",") for key, value in selector_filters.items()):
            result.append(rd)
    return result


def filter_by_tags(
    run_dirs: list[DiscoveredRunDir],
    tag_filters: list[TagFilter],
    resolved_tags: dict[str, dict[str, str]],
) -> list[DiscoveredRunDir]:
    if not tag_filters:
        return run_dirs
    result: list[DiscoveredRunDir] = []
    for rd in run_dirs:
        tags = {**rd.selectors, **resolved_tags.get(rd.relative_path, {})}
        if all(tf.matches(tags) for tf in tag_filters):
            result.append(rd)
    return result


def filter_by_changed(
    run_dirs: list[DiscoveredRunDir],
    changed_files: list[str],
) -> list[DiscoveredRunDir]:
    result: list[DiscoveredRunDir] = []
    for rd in run_dirs:
        prefix = rd.relative_path.rstrip("/") + "/"
        if any(f.startswith(prefix) or f == rd.relative_path for f in changed_files):
            result.append(rd)
    return result


def apply_filters(
    run_dirs: list[DiscoveredRunDir],
    *,
    selector_filters: dict[str, str] | None = None,
    tag_filters: list[TagFilter] | None = None,
    changed_files: list[str] | None = None,
    resolved_tags: dict[str, dict[str, str]] | None = None,
) -> list[DiscoveredRunDir]:
    result = run_dirs
    if selector_filters:
        result = filter_by_selectors(result, selector_filters)
    if tag_filters:
        result = filter_by_tags(result, tag_filters, resolved_tags or {})
    if changed_files is not None:
        result = filter_by_changed(result, changed_files)
    if not result and run_dirs:
        logger.warning("all run directories filtered out — no matches for the given filters")
    return result
