from __future__ import annotations

from tfdo._internal.inspect.description_search_logic import (
    MatchingAttributeDescription,
    search_resource_descriptions,
)
from tfdo._internal.schema.models import (
    ResourceSchema,
    SchemaAttribute,
    SchemaBlock,
    SchemaBlockType,
)


def _schema(block: SchemaBlock) -> ResourceSchema:
    return ResourceSchema(block=block)


def test_top_level_attribute_match() -> None:
    schemas = {
        "res_a": _schema(
            SchemaBlock(
                attributes={
                    "project_id": SchemaAttribute(description="The GCP project identifier", type="string"),
                    "name": SchemaAttribute(description="A human-readable name", type="string"),
                }
            )
        ),
    }
    result = search_resource_descriptions(schemas, keywords=["gcp"], row_resource_names=set())
    assert len(result) == 1
    assert result[0].name == "res_a"
    assert not result[0].found_in_rows
    assert result[0].matching_attribute_descriptions == [
        MatchingAttributeDescription(name="project_id", keywords=["gcp"], description="The GCP project identifier"),
    ]


def test_case_insensitive_substring() -> None:
    schemas = {
        "res_a": _schema(
            SchemaBlock(
                attributes={
                    "bucket": SchemaAttribute(description="Google Cloud Storage bucket name", type="string"),
                }
            )
        ),
    }
    result = search_resource_descriptions(schemas, keywords=["google", "azure"], row_resource_names=set())
    assert len(result) == 1
    assert result[0].matching_attribute_descriptions[0].keywords == ["google"]


def test_multiple_keywords_same_description() -> None:
    schemas = {
        "res_a": _schema(
            SchemaBlock(
                attributes={
                    "endpoint": SchemaAttribute(description="The GCP endpoint for Google Cloud Storage", type="string"),
                }
            )
        ),
    }
    result = search_resource_descriptions(schemas, keywords=["gcp", "google"], row_resource_names=set())
    assert len(result) == 1
    assert result[0].matching_attribute_descriptions[0].keywords == ["gcp", "google"]


def test_nested_type_child_match() -> None:
    schemas = {
        "res_a": _schema(
            SchemaBlock(
                attributes={
                    "config": SchemaAttribute(
                        description="GCP configuration block",
                        nested_type=SchemaBlock(
                            attributes={
                                "gcp_region": SchemaAttribute(description="The GCP region", type="string"),
                                "unrelated": SchemaAttribute(description="Not matching", type="string"),
                            }
                        ),
                    ),
                }
            )
        ),
    }
    result = search_resource_descriptions(schemas, keywords=["gcp"], row_resource_names=set())
    assert len(result) == 1
    descs = result[0].matching_attribute_descriptions
    assert len(descs) == 2
    assert descs[0].name == "config"
    assert descs[1].name == "config.gcp_region"


def test_block_type_child_and_block_type_description_match() -> None:
    schemas = {
        "res_a": _schema(
            SchemaBlock(
                block_types={
                    "gcs_backup": SchemaBlockType(
                        description="GCS backup configuration",
                        nesting_mode="list",
                        block=SchemaBlock(
                            attributes={
                                "bucket_name": SchemaAttribute(description="GCS bucket name", type="string"),
                                "unrelated": SchemaAttribute(description="Some other field", type="string"),
                            }
                        ),
                    ),
                }
            )
        ),
    }
    result = search_resource_descriptions(schemas, keywords=["gcs"], row_resource_names=set())
    assert len(result) == 1
    descs = result[0].matching_attribute_descriptions
    paths = [d.name for d in descs]
    assert "gcs_backup" in paths
    assert "gcs_backup.bucket_name" in paths
    assert "gcs_backup.unrelated" not in paths


def test_no_match_excludes_resource() -> None:
    schemas = {
        "res_a": _schema(
            SchemaBlock(
                attributes={
                    "name": SchemaAttribute(description="A name", type="string"),
                }
            )
        ),
    }
    result = search_resource_descriptions(schemas, keywords=["gcp"], row_resource_names=set())
    assert result == []


def test_found_in_rows() -> None:
    schemas = {
        "res_a": _schema(
            SchemaBlock(
                attributes={
                    "endpoint": SchemaAttribute(description="The GCP endpoint", type="string"),
                }
            )
        ),
        "res_b": _schema(
            SchemaBlock(
                attributes={
                    "region": SchemaAttribute(description="GCP region", type="string"),
                }
            )
        ),
    }
    result = search_resource_descriptions(schemas, keywords=["gcp"], row_resource_names={"res_a"})
    by_name = {r.name: r for r in result}
    assert by_name["res_a"].found_in_rows
    assert not by_name["res_b"].found_in_rows


def test_sorted_by_name() -> None:
    schemas = {
        "z_resource": _schema(SchemaBlock(attributes={"a": SchemaAttribute(description="GCP thing", type="string")})),
        "a_resource": _schema(SchemaBlock(attributes={"a": SchemaAttribute(description="GCP thing", type="string")})),
    }
    result = search_resource_descriptions(schemas, keywords=["gcp"], row_resource_names=set())
    assert [r.name for r in result] == ["a_resource", "z_resource"]


def test_attribute_descriptions_sorted_by_path() -> None:
    schemas = {
        "res_a": _schema(
            SchemaBlock(
                attributes={
                    "z_attr": SchemaAttribute(description="GCP z", type="string"),
                    "a_attr": SchemaAttribute(description="GCP a", type="string"),
                }
            )
        ),
    }
    result = search_resource_descriptions(schemas, keywords=["gcp"], row_resource_names=set())
    paths = [d.name for d in result[0].matching_attribute_descriptions]
    assert paths == ["a_attr", "z_attr"]
