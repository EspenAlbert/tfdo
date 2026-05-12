from __future__ import annotations

from model_lib import Event
from pydantic import Field

from tfdo._internal.hcl_entity_parser import (
    HclEntity,
    TfModuleCall,
    TfModuleExample,
    TfOutput,
    TfProvider,
    TfRequiredProviders,
    TfResource,
    TfTerraform,
    TfVariable,
)
from tfdo._internal.hcl_roundtrip import HclAttrRef, HclValue, HclVarRef


class RunDirSelection(Event):
    include_resources: set[tuple[str, str]] = Field(default_factory=set)
    include_modules: set[str] = Field(default_factory=set)
    include_providers: set[str] = Field(default_factory=set)

    @classmethod
    def from_example(cls, example: TfModuleExample) -> RunDirSelection:
        return cls(
            include_resources={(e.type, e.name) for e in example.entities if isinstance(e, TfResource)},
            include_modules={e.name for e in example.entities if isinstance(e, TfModuleCall)},
            include_providers={e.name for e in example.entities if isinstance(e, TfProvider)},
        )


def _collect_var_refs_from_value(value: HclValue, refs: set[str]) -> None:
    if isinstance(value, HclVarRef):
        name = value.path.removeprefix("var.")
        refs.add(name)
    elif isinstance(value, HclAttrRef):
        pass
    elif isinstance(value, list):
        for item in value:
            _collect_var_refs_from_value(item, refs)
    elif isinstance(value, dict):
        for item in value.values():
            _collect_var_refs_from_value(item, refs)


def collect_var_refs(entities: list[HclEntity]) -> set[str]:
    refs: set[str] = set()
    for entity in entities:
        if isinstance(entity, TfResource):
            for value in entity.attrs.values():
                _collect_var_refs_from_value(value, refs)
        elif isinstance(entity, TfModuleCall):
            for value in entity.attrs.values():
                _collect_var_refs_from_value(value, refs)
            if entity.source:
                pass
        elif isinstance(entity, TfOutput):
            _collect_var_refs_from_value(entity.value, refs)
    return refs


def select_entities(example: TfModuleExample, selection: RunDirSelection) -> list[HclEntity]:
    kept_primary: list[HclEntity] = []

    for entity in example.entities:
        if isinstance(entity, TfResource) and (entity.type, entity.name) in selection.include_resources:
            kept_primary.append(entity)
        elif isinstance(entity, TfModuleCall) and entity.name in selection.include_modules:
            kept_primary.append(entity)
        elif isinstance(entity, TfProvider) and entity.name in selection.include_providers:
            kept_primary.append(entity)
        elif isinstance(entity, TfTerraform | TfRequiredProviders | TfOutput):
            kept_primary.append(entity)

    referenced_vars = collect_var_refs(kept_primary)

    result: list[HclEntity] = list(kept_primary)
    for entity in example.entities:
        if isinstance(entity, TfVariable) and entity.name in referenced_vars:
            result.append(entity)

    return result
