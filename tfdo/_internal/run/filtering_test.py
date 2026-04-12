from __future__ import annotations

from pathlib import Path

from tfdo._internal.run.discovery import DiscoveredRunDir
from tfdo._internal.run.filtering import (
    TagFilter,
    apply_filters,
    filter_by_changed,
    filter_by_selectors,
    filter_by_tags,
)


def _run_dir(rel: str, **selectors: str) -> DiscoveredRunDir:
    return DiscoveredRunDir(path=Path(f"/repo/{rel}"), relative_path=rel, selectors=selectors)


def test_filter_by_selectors_single():
    dirs = [_run_dir("envs/dev/api", env="dev", app="api"), _run_dir("envs/prod/api", env="prod", app="api")]
    result = filter_by_selectors(dirs, {"env": "dev"})
    assert [r.relative_path for r in result] == ["envs/dev/api"]


def test_filter_by_selectors_comma_or():
    dirs = [
        _run_dir("envs/dev/api", env="dev"),
        _run_dir("envs/staging/api", env="staging"),
        _run_dir("envs/prod/api", env="prod"),
    ]
    result = filter_by_selectors(dirs, {"env": "dev,staging"})
    assert len(result) == 2


def test_filter_by_selectors_multi_and():
    dirs = [_run_dir("envs/dev/api", env="dev", app="api"), _run_dir("envs/dev/web", env="dev", app="web")]
    result = filter_by_selectors(dirs, {"env": "dev", "app": "api"})
    assert len(result) == 1
    assert result[0].selectors["app"] == "api"


def test_filter_by_tags():
    dirs = [_run_dir("envs/dev/api", env="dev"), _run_dir("envs/prod/api", env="prod")]
    resolved_tags = {"envs/dev/api": {"tier": "low"}, "envs/prod/api": {"tier": "critical"}}
    tags = [TagFilter(key="tier", values=["critical"])]
    result = filter_by_tags(dirs, tags, resolved_tags)
    assert [r.relative_path for r in result] == ["envs/prod/api"]


def test_filter_by_tags_or_within_key():
    dirs = [_run_dir("a", env="dev"), _run_dir("b", env="prod")]
    resolved_tags = {"a": {"tier": "low"}, "b": {"tier": "critical"}}
    tags = [TagFilter(key="tier", values=["critical", "high"])]
    result = filter_by_tags(dirs, tags, resolved_tags)
    assert len(result) == 1


def test_filter_by_changed():
    dirs = [_run_dir("envs/dev/api"), _run_dir("envs/prod/api")]
    changed = ["envs/dev/api/main.tf", "unrelated/file.py"]
    result = filter_by_changed(dirs, changed)
    assert [r.relative_path for r in result] == ["envs/dev/api"]


def test_apply_filters_warns_on_zero(caplog):
    dirs = [_run_dir("envs/dev/api", env="dev")]
    result = apply_filters(dirs, selector_filters={"env": "prod"})
    assert result == []
    assert "filtered out" in caplog.text


def test_tag_filter_parse():
    tf = TagFilter.parse("tier=critical,high")
    assert tf.key == "tier"
    assert tf.values == ["critical", "high"]
