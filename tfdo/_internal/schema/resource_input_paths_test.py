from __future__ import annotations

import json
from pathlib import Path

from tfdo._internal.schema.models import ResourceSchema
from tfdo._internal.schema.resource_input_paths import resource_schema_input_paths

_FIXTURE_DIR = Path(__file__).resolve().parent / "resource_input_paths_test"

_SYNTHETIC_SCHEMA = {
    "version": 0,
    "block": {
        "attributes": {
            "outer": {
                "optional": True,
                "nested_type": {
                    "nesting_mode": "single",
                    "attributes": {
                        "inner": {"type": "string", "optional": True},
                    },
                },
            },
            "plain_map": {
                "optional": True,
                "type": ["map", "string"],
            },
            "computed_field": {"type": "string", "computed": True},
        },
        "block_types": {
            "disk": {
                "nesting_mode": "list",
                "block": {
                    "attributes": {
                        "size": {"type": "number", "required": True},
                        "shadow": {"type": "string", "computed": True},
                    },
                    "block_types": {
                        "encryption": {
                            "nesting_mode": "single",
                            "block": {
                                "attributes": {
                                    "key_id": {"type": "string", "optional": True},
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}


def test_backward_compat_default_depth() -> None:
    schema = ResourceSchema.model_validate(_SYNTHETIC_SCHEMA)
    paths = resource_schema_input_paths(schema)
    assert "outer.inner" in paths
    assert "plain_map" in paths
    assert "disk.size" in paths
    assert "disk.shadow" not in paths
    assert "disk.encryption" in paths, "nested block_type emitted as leaf at max_depth=1"
    assert "disk.encryption.key_id" not in paths, "does not recurse into encryption at depth=1"


def test_deeper_nesting_and_include_computed() -> None:
    schema = ResourceSchema.model_validate(_SYNTHETIC_SCHEMA)
    paths = resource_schema_input_paths(schema, max_depth=10, include_computed=True)
    assert "disk.encryption.key_id" in paths
    assert "disk.shadow" in paths
    assert "computed_field" in paths


def test_mongodbatlas_project_fixture_golden() -> None:
    raw = json.loads((_FIXTURE_DIR / "mongodbatlas_project_resource_schema.json").read_text())
    schema = ResourceSchema.model_validate(raw)
    paths = resource_schema_input_paths(schema)
    assert "tags" in paths
    for p in ("limits.name", "limits.value", "teams.team_id", "teams.role_names"):
        assert p in paths
    assert "cluster_count" not in paths
    assert not any(x.startswith("ip_addresses.") for x in paths)
    assert "ip_addresses" not in paths
