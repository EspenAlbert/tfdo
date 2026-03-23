from __future__ import annotations

from pathlib import Path

from tfdo._internal.schema import cache as schema_cache


def test_cache_relative_path_includes_local_name_source_segments_and_version() -> None:
    p1 = schema_cache.cache_relative_path(
        local_name="aws",
        source="hashicorp/aws",
        resolved_version="5.0.0",
    )
    assert p1 == Path("aws") / "hashicorp" / "aws" / "5.0.0.json"
    p2 = schema_cache.cache_relative_path(
        local_name="aws",
        source="acme/aws",
        resolved_version="5.0.0",
    )
    assert p2 == Path("aws") / "acme" / "aws" / "5.0.0.json"


def test_try_read_cached_schema_invalid_json_returns_none(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    p.write_text("{not json", encoding="utf-8")
    assert schema_cache.try_read_cached_schema(p) is None


def test_read_resolved_version_from_lock(tmp_path: Path) -> None:
    (tmp_path / ".terraform.lock.hcl").write_text(
        """
provider "registry.terraform.io/mongodb/mongodbatlas" {
  version = "1.2.3"
}
""",
        encoding="utf-8",
    )
    got = schema_cache.read_resolved_version_from_lock(
        workspace_root=tmp_path,
        source="mongodb/mongodbatlas",
    )
    assert got == "1.2.3"


def test_write_then_read_cached_schema(tmp_path: Path) -> None:
    rel = Path("p") / "ns" / "t" / "1.0.0.json"
    payload = {"format_version": "1.0", "provider_schemas": {}}
    schema_cache.write_cached_schema(tmp_path, rel, payload)
    full = tmp_path / rel
    assert schema_cache.try_read_cached_schema(full) == payload
