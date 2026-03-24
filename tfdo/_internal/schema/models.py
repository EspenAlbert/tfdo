from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SchemaAttribute(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str | list | dict | None = None
    description: str | None = None
    description_kind: str | None = None
    optional: bool | None = None
    required: bool | None = None
    computed: bool | None = None
    deprecated: bool | None = None
    sensitive: bool | None = None
    nested_type: SchemaBlock | None = None
    default: object | None = None
    enum: list[object] | None = None
    allowed_values: list[object] | None = None
    force_new: bool | None = None
    conflicts_with: list[str] | None = None
    exactly_one_of: list[str] | None = None
    at_least_one_of: list[str] | None = None
    required_with: list[str] | None = None
    deprecated_message: str | None = None
    validators: list[dict] | None = None
    element_type: str | dict | None = None


class SchemaBlockType(BaseModel):
    model_config = ConfigDict(extra="ignore")

    block: SchemaBlock
    nesting_mode: str
    min_items: int | None = None
    max_items: int | None = None
    required: bool | None = None
    optional: bool | None = None
    description_kind: str | None = None
    deprecated: bool | None = None
    description: str | None = None
    default: object | None = None
    validators: list[dict] | None = None


class SchemaBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")

    attributes: dict[str, SchemaAttribute] | None = None
    block_types: dict[str, SchemaBlockType] | None = None
    description_kind: str | None = None
    description: str | None = None
    deprecated: bool | None = None
    nesting_mode: str | None = None


class ResourceSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    block: SchemaBlock
    version: int | None = None
    description_kind: str | None = None


SchemaAttribute.model_rebuild()
SchemaBlockType.model_rebuild()
SchemaBlock.model_rebuild()
