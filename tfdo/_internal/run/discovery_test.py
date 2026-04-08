from __future__ import annotations

from pathlib import Path

import pytest

from tfdo._internal.config.config_resolution import ResolvedConfig
from tfdo._internal.config.enums import TagsInject
from tfdo._internal.run.discovery import (
    DiscoveredRunDir,
    build_run_dir_contexts,
    discover_run_dirs,
    has_backend_block,
    parse_discovery_pattern,
)
from tfdo._internal.settings import CheckConfig

TF_BACKEND = 'terraform {\n  backend "s3" {\n    bucket = "my-bucket"\n  }\n}\n'
TF_NO_BACKEND = 'resource "aws_instance" "example" {\n  ami = "abc"\n}\n'


def test_parse_pattern_required_segments():
    p = parse_discovery_pattern("envs/{env}/{app}")
    assert p.selector_names == ["env", "app"]
    assert p.optional_selectors == set()
    result = p.match("envs/dev/api")
    assert result == {"env": "dev", "app": "api"}


def test_parse_pattern_optional_segment():
    p = parse_discovery_pattern("{team}?/envs/{env}")
    assert "team" in p.optional_selectors
    assert p.match("platform/envs/dev") == {"team": "platform", "env": "dev"}
    assert p.match("envs/dev") == {"env": "dev"}


def test_parse_pattern_rejects_multiple_optional():
    with pytest.raises(ValueError, match="max one optional"):
        parse_discovery_pattern("{a}?/{b}?")


def test_parse_pattern_no_captures():
    p = parse_discovery_pattern("envs/shared")
    assert p.selector_names == []
    assert p.match("envs/shared") == {}
    assert p.match("envs/other") is None


def test_match_returns_none_on_mismatch():
    p = parse_discovery_pattern("envs/{env}/{app}")
    assert p.match("other/dev/api") is None
    assert p.match("envs/dev") is None


def test_has_backend_block(tmp_path: Path):
    (tmp_path / "main.tf").write_text(TF_BACKEND)
    assert has_backend_block(tmp_path)


def test_has_backend_block_negative(tmp_path: Path):
    (tmp_path / "main.tf").write_text(TF_NO_BACKEND)
    assert not has_backend_block(tmp_path)


def test_has_backend_block_skips_unparseable(tmp_path: Path):
    (tmp_path / "bad.tf").write_text("{{{{invalid hcl")
    assert not has_backend_block(tmp_path)


def test_discover_run_dirs(tmp_path: Path):
    pattern = parse_discovery_pattern("envs/{env}/{app}")
    for env, app in [("dev", "api"), ("dev", "web"), ("staging", "api")]:
        d = tmp_path / "envs" / env / app
        d.mkdir(parents=True)
        (d / "main.tf").write_text(TF_BACKEND)
    no_backend = tmp_path / "envs" / "dev" / "worker"
    no_backend.mkdir(parents=True)
    (no_backend / "main.tf").write_text(TF_NO_BACKEND)

    results = discover_run_dirs(tmp_path, pattern)
    paths = [r.relative_path for r in results]
    assert paths == ["envs/dev/api", "envs/dev/web", "envs/staging/api"]
    assert results[0].selectors == {"env": "dev", "app": "api"}


def test_discover_run_dirs_optional_segment(tmp_path: Path):
    pattern = parse_discovery_pattern("{team}?/envs/{env}")
    for parts in [("platform", "envs", "dev"), ("envs", "staging")]:
        d = tmp_path.joinpath(*parts)
        d.mkdir(parents=True)
        (d / "main.tf").write_text(TF_BACKEND)

    results = discover_run_dirs(tmp_path, pattern)
    assert len(results) == 2
    by_path = {r.relative_path: r.selectors for r in results}
    assert by_path["envs/staging"] == {"env": "staging"}
    assert by_path["platform/envs/dev"] == {"team": "platform", "env": "dev"}


def test_build_run_dir_contexts():
    discovered = [
        DiscoveredRunDir(
            path=Path("/repo/envs/dev/api"), relative_path="envs/dev/api", selectors={"env": "dev", "app": "api"}
        ),
    ]
    config = ResolvedConfig(
        binary="terraform",
        tf_version=None,
        backend=None,
        tags={"project": "myproj"},
        var_files=[],
        tags_inject=TagsInject.NEVER,
        hook_configs=[],
        dependencies=[],
        check=CheckConfig(),
    )
    contexts = build_run_dir_contexts(discovered, config, "owner", "repo")
    assert len(contexts) == 1
    ctx = contexts[0]
    assert ctx.name == "api"
    assert ctx.path == "envs/dev/api"
    assert ctx.repo_owner == "owner"
    assert ctx.tags == {"project": "myproj", "env": "dev", "app": "api"}
