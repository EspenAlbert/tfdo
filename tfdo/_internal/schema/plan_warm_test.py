from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tfdo._internal.hcl_read import REGISTRY_HOST_PREFIX
from tfdo._internal.output.models import Change, PlanOutput, ResourceChange
from tfdo._internal.schema import cache as schema_cache
from tfdo._internal.schema import plan_warm as plan_warm_module
from tfdo._internal.schema.plan_warm import (
    ProviderCacheMiss,
    cache_misses_for_providers,
    providers_in_plan,
    warm_plan_schema_cache,
    write_provider_schema_caches,
)
from tfdo._internal.settings import TfDoSettings

_AWS_PROVIDER = f"{REGISTRY_HOST_PREFIX}hashicorp/aws"
_ATLAS_PROVIDER = f"{REGISTRY_HOST_PREFIX}mongodb/mongodbatlas"


def _resource_change(*, provider_name: str, address: str = "aws_s3_bucket.example") -> ResourceChange:
    return ResourceChange(
        address=address,
        mode="managed",
        type="aws_s3_bucket",
        name="example",
        provider_name=provider_name,
        change=Change(actions=["create"], after={"bucket": "x"}),
    )


def test_providers_in_plan_collects_changes_and_drift() -> None:
    plan = PlanOutput(
        format_version="1.2",
        errored=False,
        resource_changes=[_resource_change(provider_name=_AWS_PROVIDER)],
        resource_drift=[
            _resource_change(
                provider_name=_ATLAS_PROVIDER,
                address="mongodbatlas_project.this",
            )
        ],
    )
    assert providers_in_plan(plan) == frozenset({_AWS_PROVIDER, _ATLAS_PROVIDER})


def test_cache_misses_for_providers_skips_hits_and_unknown_lock_entries(tmp_path: Path) -> None:
    lock_versions = {_AWS_PROVIDER: "5.0.0", _ATLAS_PROVIDER: "2.8.0"}
    cache_root = tmp_path / "schemas"
    payload = {"format_version": "1.0", "provider_schemas": {}}
    rel = schema_cache.cache_relative_path(local_name="aws", source="hashicorp/aws", resolved_version="5.0.0")
    schema_cache.write_cached_schema(cache_root, rel, payload)

    misses = cache_misses_for_providers(
        lock_versions=lock_versions,
        providers=frozenset({_AWS_PROVIDER, _ATLAS_PROVIDER}),
        schema_cache_dir=cache_root,
    )
    assert misses == [
        ProviderCacheMiss(
            provider_addr=_ATLAS_PROVIDER,
            source="mongodb/mongodbatlas",
            version="2.8.0",
            local_name="mongodbatlas",
        )
    ]


def test_write_provider_schema_caches_writes_single_provider_payload(tmp_path: Path) -> None:
    payload = {
        "format_version": "1.0",
        "provider_schemas": {
            _AWS_PROVIDER: {
                "provider": {"version": 0},
                "resource_schemas": {"aws_s3_bucket": {"version": 0, "block": {"attributes": {}}}},
            }
        },
    }
    misses = [
        ProviderCacheMiss(
            provider_addr=_AWS_PROVIDER,
            source="hashicorp/aws",
            version="5.0.0",
            local_name="aws",
        )
    ]
    cache_root = tmp_path / "schemas"
    write_provider_schema_caches(payload=payload, misses=misses, schema_cache_dir=cache_root)
    rel = schema_cache.cache_relative_path(local_name="aws", source="hashicorp/aws", resolved_version="5.0.0")
    cached = schema_cache.try_read_cached_schema(cache_root / rel)
    assert cached is not None
    assert set(cached.get("provider_schemas", {})) == {_AWS_PROVIDER}


def test_warm_plan_schema_cache_writes_on_miss(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    lock_path = tmp_path / ".terraform.lock.hcl"
    lock_path.write_text(f'provider "{_AWS_PROVIDER}" {{ version = "5.0.0" }}\n', encoding="utf-8")
    plan = PlanOutput(
        format_version="1.2",
        errored=False,
        resource_changes=[_resource_change(provider_name=_AWS_PROVIDER)],
    )
    payload = {
        "format_version": "1.0",
        "provider_schemas": {
            _AWS_PROVIDER: {
                "provider": {"version": 0},
                "resource_schemas": {"aws_s3_bucket": {"version": 0, "block": {"attributes": {}}}},
            }
        },
    }
    fetch_mock = MagicMock(return_value=payload)
    monkeypatch.setattr(plan_warm_module, "providers_schema_json_or_raise", fetch_mock)

    settings = TfDoSettings(work_dir=tmp_path)
    cache_root = tmp_path / "schemas"
    warm_plan_schema_cache(
        settings,
        lock_path=lock_path,
        plan=plan,
        schema_cache_dir=cache_root,
    )
    fetch_mock.assert_called_once()
    rel = schema_cache.cache_relative_path(local_name="aws", source="hashicorp/aws", resolved_version="5.0.0")
    assert schema_cache.try_read_cached_schema(cache_root / rel) is not None


def test_warm_plan_schema_cache_logs_warning_on_fetch_failure(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    caplog.set_level(logging.WARNING)
    lock_path = tmp_path / ".terraform.lock.hcl"
    lock_path.write_text(f'provider "{_AWS_PROVIDER}" {{ version = "5.0.0" }}\n', encoding="utf-8")
    plan = PlanOutput(
        format_version="1.2",
        errored=False,
        resource_changes=[_resource_change(provider_name=_AWS_PROVIDER)],
    )
    monkeypatch.setattr(
        plan_warm_module,
        "providers_schema_json_or_raise",
        MagicMock(side_effect=RuntimeError("providers schema failed")),
    )

    warm_plan_schema_cache(
        TfDoSettings(work_dir=tmp_path),
        lock_path=lock_path,
        plan=plan,
        schema_cache_dir=tmp_path / "schemas",
    )
    assert any("schema cache warm failed" in r.message for r in caplog.records)
