from __future__ import annotations

import json
from pathlib import Path

from hcl2.api import load as hcl2_load

from tfdo._internal.inspect.hcl_schema_paths import collect_resource_body_paths_assisted
from tfdo._internal.schema.models import ResourceSchema
from tfdo._internal.schema.resource_input_paths import resource_schema_input_paths

_FIXTURE_DIR = Path(__file__).resolve().parent / "hcl_schema_paths_test"


def test_collect_resource_body_paths_unknown_and_invalid() -> None:
    schema = ResourceSchema.model_validate(
        {
            "version": 0,
            "block": {
                "attributes": {
                    "a": {"type": "string", "required": True},
                    "m": {
                        "optional": True,
                        "type": ["map", "string"],
                    },
                },
            },
        }
    )
    r = collect_resource_body_paths_assisted({"a": "x", "ghost": 1, "m": "bad"}, schema)
    assert "ghost" in r.unknown_in_config
    assert "m" in r.invalid_in_config
    assert "a" in r.attribute_paths


def test_collect_assisted_hits_block_list_dynamic_and_nested_list() -> None:
    schema = ResourceSchema.model_validate(
        {
            "version": 0,
            "block": {
                "attributes": {
                    "plain": {"type": "string", "optional": True},
                    "tags": {"type": ["map", "string"], "optional": True},
                    "items": {
                        "optional": True,
                        "nested_type": {
                            "nesting_mode": "list",
                            "attributes": {
                                "name": {"type": "string", "optional": True},
                                "id": {"type": "string", "computed": True},
                            },
                        },
                    },
                    "computed_top": {"type": "string", "computed": True},
                },
                "block_types": {
                    "disk": {
                        "nesting_mode": "list",
                        "block": {
                            "attributes": {
                                "size": {"type": "number", "required": True},
                            },
                        },
                    },
                },
            },
        }
    )
    body = {
        "disk": "not_list",
        "plain": "v",
        "tags": {"a": "b"},
        "items": [{"name": "n", "ghost": 1, "id": "x"}],
        "computed_top": "set",
        "dynamic": [{"disk": {"content": [{"size": 9}]}}],
    }
    r = collect_resource_body_paths_assisted(body, schema)
    assert "disk" in r.invalid_in_config
    assert "items.ghost" in r.unknown_in_config
    assert "items.id" in r.invalid_in_config
    assert "computed_top" in r.invalid_in_config
    assert "plain" in r.attribute_paths
    assert "tags" in r.attribute_paths
    assert "items.name" in r.attribute_paths
    assert "disk.size" in r.attribute_paths


def test_mongodbatlas_advanced_cluster_assisted_subset_of_schema_paths() -> None:
    schema = ResourceSchema.model_validate(
        json.loads((_FIXTURE_DIR / "mongodbatlas_advanced_cluster_schema.json").read_text())
    )
    allowed = resource_schema_input_paths(schema)
    with (_FIXTURE_DIR / "mongodbatlas_advanced_cluster.tf").open(encoding="utf-8") as f:
        parsed = hcl2_load(f)
    body = parsed["resource"][0]["mongodbatlas_advanced_cluster"]["this"]
    r = collect_resource_body_paths_assisted(body, schema)
    assert not (r.attribute_paths - allowed)
    assert "tags" in r.attribute_paths
    assert "advanced_configuration.javascript_enabled" in r.attribute_paths
    assert "replication_specs.region_configs" in r.attribute_paths
    assert not any(p.startswith("tags.") for p in r.attribute_paths)
