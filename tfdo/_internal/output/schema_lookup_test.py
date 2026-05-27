from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from tfdo._internal.hcl_read import REGISTRY_HOST_PREFIX
from tfdo._internal.output.schema_lookup import (
    attribute_collection_kind,
    build_schema_lookups,
    resource_schema_required_attrs,
)
from tfdo._internal.schema import cache as schema_cache
from tfdo._internal.schema.models import ResourceSchema

_FIXTURE_DIR = Path(__file__).resolve().parent / "schema_lookup_test"
_AWS_PROVIDER = f"{REGISTRY_HOST_PREFIX}hashicorp/aws"

_LIST_NESTED_SCHEMA = {
    "version": 0,
    "block": {
        "attributes": {
            "items": {
                "optional": True,
                "nested_type": {
                    "nesting_mode": "list",
                    "attributes": {
                        "name": {"type": "string", "optional": True},
                    },
                },
            },
        },
    },
}


def _load_fixture(name: str) -> ResourceSchema:
    raw = json.loads((_FIXTURE_DIR / name).read_text())
    return ResourceSchema.model_validate(raw)


def test_resource_schema_required_attrs() -> None:
    assert resource_schema_required_attrs(_load_fixture("aws_s3_bucket_resource_schema.json")) == frozenset({"bucket"})
    assert resource_schema_required_attrs(_load_fixture("aws_security_group_resource_schema.json")) == frozenset(
        {"name"}
    )


@pytest.mark.parametrize(
    ("fixture", "path", "expected"),
    [
        ("aws_security_group_resource_schema.json", ("ingress",), "set"),
        (None, ("items",), "list"),
        ("aws_security_group_resource_schema.json", ("nonexistent",), None),
    ],
)
def test_attribute_collection_kind(
    fixture: str | None,
    path: tuple[str | int, ...],
    expected: str | None,
) -> None:
    schema = ResourceSchema.model_validate(_LIST_NESTED_SCHEMA) if fixture is None else _load_fixture(fixture)
    assert attribute_collection_kind(schema, path) == expected


def test_build_schema_lookups_miss_and_hit(tmp_path: Path) -> None:
    lock = tmp_path / ".terraform.lock.hcl"
    lock.write_text(
        f"""
provider "{_AWS_PROVIDER}" {{
  version = "5.0.0"
}}
""",
        encoding="utf-8",
    )
    cache_root = tmp_path / "schemas"
    miss = build_schema_lookups(workspace_root=tmp_path, schema_cache_dir=cache_root)
    assert miss.required_attrs(_AWS_PROVIDER, "aws_s3_bucket") == frozenset()
    assert miss.collection_kind(_AWS_PROVIDER, "aws_s3_bucket", ("bucket",)) is None

    bucket_schema = _load_fixture("aws_s3_bucket_resource_schema.json")
    payload = {
        "format_version": "1.0",
        "provider_schemas": {
            "registry.terraform.io/hashicorp/aws": {
                "provider": {"version": 0},
                "resource_schemas": {"aws_s3_bucket": bucket_schema.model_dump(mode="json", exclude_none=True)},
            },
        },
    }
    rel = schema_cache.cache_relative_path(local_name="aws", source="hashicorp/aws", resolved_version="5.0.0")
    schema_cache.write_cached_schema(cache_root, rel, payload)

    hit = build_schema_lookups(workspace_root=tmp_path, schema_cache_dir=cache_root)
    assert hit.required_attrs(_AWS_PROVIDER, "aws_s3_bucket") == frozenset({"bucket"})


def test_build_schema_lookups_finds_lock_in_parent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    run_dir = repo / "envs" / "dev" / "run"
    run_dir.mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / ".terraform.lock.hcl").write_text(
        f'provider "{_AWS_PROVIDER}" {{ version = "5.0.0" }}\n',
        encoding="utf-8",
    )
    cache_root = tmp_path / "schemas"
    bucket_schema = _load_fixture("aws_s3_bucket_resource_schema.json")
    payload = {
        "format_version": "1.0",
        "provider_schemas": {
            "registry.terraform.io/hashicorp/aws": {
                "provider": {"version": 0},
                "resource_schemas": {"aws_s3_bucket": bucket_schema.model_dump(mode="json", exclude_none=True)},
            },
        },
    }
    rel = schema_cache.cache_relative_path(local_name="aws", source="hashicorp/aws", resolved_version="5.0.0")
    schema_cache.write_cached_schema(cache_root, rel, payload)

    lookups = build_schema_lookups(workspace_root=run_dir, schema_cache_dir=cache_root)
    assert lookups.required_attrs(_AWS_PROVIDER, "aws_s3_bucket") == frozenset({"bucket"})


def test_build_schema_lookups_warns_on_duplicate_cache(caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    caplog.set_level(logging.WARNING)
    (tmp_path / ".terraform.lock.hcl").write_text(
        f'provider "{_AWS_PROVIDER}" {{ version = "5.0.0" }}\n',
        encoding="utf-8",
    )
    cache_root = tmp_path / "schemas"
    payload = {"format_version": "1.0", "provider_schemas": {}}
    for local in ("aws", "aws_alt"):
        rel = schema_cache.cache_relative_path(local_name=local, source="hashicorp/aws", resolved_version="5.0.0")
        schema_cache.write_cached_schema(cache_root, rel, payload)

    build_schema_lookups(workspace_root=tmp_path, schema_cache_dir=cache_root)
    assert any("multiple schema cache files" in r.message for r in caplog.records)
