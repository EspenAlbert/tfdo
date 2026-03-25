from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from tfdo._internal.inspect import api_coverage_logic
from tfdo._internal.inspect.api_coverage_logic import (
    ApiCoverageInput,
    CoverageConfig,
    ResolvedKnown,
    ResourceKnown,
    _build_gap_report,
    inspect_api_coverage,
)
from tfdo._internal.schema.inspect_logic import load_provider_resource_schemas_with_meta
from tfdo._internal.schema.models import ResourceSchema
from tfdo._internal.settings import TfDoSettings

_SIMPLE_SCHEMA = ResourceSchema.model_validate(
    {
        "version": 0,
        "block": {
            "attributes": {
                "cluster_type": {"type": "string", "optional": True},
                "disk_size_gb": {"type": "number", "optional": True},
                "name": {"type": "string", "required": True},
                "state_name": {"type": "string", "computed": True},
            }
        },
    }
)


def test_build_gap_report_basic() -> None:
    api_paths = {"clusterType", "diskSizeGB", "name", "unknownField"}
    tf_paths = frozenset({"cluster_type", "disk_size_gb", "name"})
    resolved = ResolvedKnown()
    report = _build_gap_report("res_api", "res_tf", api_paths, tf_paths, resolved)
    assert report.matched == 3
    assert report.api_only == ["unknownField"]
    assert not report.schema_only
    assert report.coverage_pct > 0


def test_build_gap_report_known_gaps_filtered() -> None:
    api_paths = {"clusterType", "links.href"}
    tf_paths = frozenset({"cluster_type", "state_name"})
    resolved = ResolvedKnown(
        known_schema_only={"state_name"},
        known_spec_only={"links.href"},
    )
    report = _build_gap_report("res_api", "res_tf", api_paths, tf_paths, resolved)
    assert report.matched == 1
    assert not report.api_only
    assert not report.schema_only


def test_coverage_config_resolve_merges_global_and_per_resource() -> None:
    config = CoverageConfig(
        known_schema_only=["state_name"],
        known_spec_only=["links.href"],
        name_overrides={"a": "b"},
        resources={
            "res_api": ResourceKnown(
                known_schema_only=["extra_field"],
                name_overrides={"c": "d"},
            )
        },
    )
    resolved = config.resolve("res_api")
    assert "state_name" in resolved.known_schema_only
    assert "extra_field" in resolved.known_schema_only
    assert resolved.name_overrides == {"a": "b", "c": "d"}

    default = config.resolve("unknown_api")
    assert default.known_schema_only == {"state_name"}


def _write_api_attrs(tmp_path: Path, resources: list[dict]) -> Path:
    p = tmp_path / "api-attrs.json"
    p.write_text(json.dumps({"provider": "test", "resources": resources}))
    return p


def test_include_exclude_filtering(tmp_path: Path) -> None:
    resources = [
        {"resource_type": "res_a", "all_paths": ["fieldX"]},
        {"resource_type": "res_b", "all_paths": ["fieldY"]},
        {"resource_type": "res_c", "all_paths": ["fieldZ"]},
    ]
    api_file = _write_api_attrs(tmp_path, resources)
    config = CoverageConfig(include_resources=["res_a", "res_b"], exclude_resources=["res_b"])

    module_name = api_coverage_logic.__name__
    mock_schemas = {"res_a": _SIMPLE_SCHEMA}
    with patch(
        f"{module_name}.{load_provider_resource_schemas_with_meta.__name__}", return_value=(mock_schemas, "1.0")
    ):
        result = inspect_api_coverage(
            ApiCoverageInput(
                settings=TfDoSettings(work_dir=tmp_path),
                api_attributes_file=api_file,
                provider="test",
                coverage_config=config,
            )
        )
    types = [r.api_resource_type for r in result.resources]
    assert "res_a" in types
    assert "res_b" not in types
    assert "res_c" not in types
