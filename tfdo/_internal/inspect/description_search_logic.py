from __future__ import annotations

from pydantic import BaseModel

from tfdo._internal.schema.models import ResourceSchema, SchemaBlock


class MatchingAttributeDescription(BaseModel):
    name: str
    keywords: list[str]
    description: str


class MatchingSchemaResource(BaseModel):
    name: str
    found_in_rows: bool
    matching_attribute_descriptions: list[MatchingAttributeDescription]


def _walk_block_descriptions(
    block: SchemaBlock,
    prefix: str,
    keywords_lower: list[str],
    matches: list[MatchingAttributeDescription],
) -> None:
    for attr_name, attr in sorted((block.attributes or {}).items()):
        path = f"{prefix}.{attr_name}" if prefix else attr_name
        if attr.description:
            matched = [k for k in keywords_lower if k in attr.description.lower()]
            if matched:
                matches.append(MatchingAttributeDescription(name=path, keywords=matched, description=attr.description))
        if attr.nested_type is not None:
            _walk_block_descriptions(attr.nested_type, path, keywords_lower, matches)
    for bt_name, bt in sorted((block.block_types or {}).items()):
        path = f"{prefix}.{bt_name}" if prefix else bt_name
        if bt.description:
            matched = [k for k in keywords_lower if k in bt.description.lower()]
            if matched:
                matches.append(MatchingAttributeDescription(name=path, keywords=matched, description=bt.description))
        _walk_block_descriptions(bt.block, path, keywords_lower, matches)


def search_resource_descriptions(
    resource_schemas: dict[str, ResourceSchema],
    *,
    keywords: list[str],
    row_resource_names: set[str],
) -> list[MatchingSchemaResource]:
    keywords_lower = [k.lower() for k in keywords]
    results: list[MatchingSchemaResource] = []
    for rname in sorted(resource_schemas):
        schema = resource_schemas[rname]
        matches: list[MatchingAttributeDescription] = []
        _walk_block_descriptions(schema.block, "", keywords_lower, matches)
        if matches:
            results.append(
                MatchingSchemaResource(
                    name=rname,
                    found_in_rows=rname in row_resource_names,
                    matching_attribute_descriptions=matches,
                )
            )
    return results
