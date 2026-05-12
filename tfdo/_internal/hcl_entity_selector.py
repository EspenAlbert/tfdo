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


def entity_key(entity: HclEntity) -> tuple:
    match entity:
        case TfResource(type=t, name=n):
            return (type(entity), t, n)
        case TfModuleCall(name=n) | TfProvider(name=n) | TfVariable(name=n) | TfOutput(name=n):
            return (type(entity), n)
        case _:
            return (type(entity),)


def dedup_new_entities(existing: list[HclEntity], candidates: list[HclEntity]) -> list[HclEntity]:
    existing_keys = {entity_key(e) for e in existing}
    return [
        e
        for e in candidates
        # TfTerraform and TfRequiredProviders are both nested inside terraform{} and are
        # never copied as blocks — required_providers are merged individually via
        # update_required_providers in merge_run_dir.
        if not isinstance(e, TfTerraform | TfRequiredProviders) and entity_key(e) not in existing_keys
    ]


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
    match value:
        case HclVarRef(path=path):
            refs.add(path.removeprefix("var."))
        case list():
            for item in value:
                _collect_var_refs_from_value(item, refs)
        case dict():
            for item in value.values():
                _collect_var_refs_from_value(item, refs)


def collect_var_refs(entities: list[HclEntity]) -> set[str]:
    refs: set[str] = set()
    for entity in entities:
        match entity:
            case TfResource(attrs=attrs) | TfModuleCall(attrs=attrs):
                for value in attrs.values():
                    _collect_var_refs_from_value(value, refs)
            case TfOutput(value=value):
                _collect_var_refs_from_value(value, refs)
    return refs


def _output_references_kept(output: TfOutput, selection: RunDirSelection) -> bool:
    match output.value:
        case HclAttrRef(path=path):
            parts = path.split(".")
            if len(parts) >= 2 and parts[0] == "module":
                return parts[1] in selection.include_modules
            if len(parts) >= 2:
                return (parts[0], parts[1]) in selection.include_resources
    return False


def select_entities(example: TfModuleExample, selection: RunDirSelection) -> list[HclEntity]:
    kept_primary: list[HclEntity] = []

    for entity in example.entities:
        match entity:
            case TfResource(type=t, name=n) if (t, n) in selection.include_resources:
                kept_primary.append(entity)
            case TfModuleCall(name=n) if n in selection.include_modules:
                kept_primary.append(entity)
            case TfProvider(name=n) if n in selection.include_providers:
                kept_primary.append(entity)
            case TfTerraform() | TfRequiredProviders():
                kept_primary.append(entity)

    referenced_vars = collect_var_refs(kept_primary)

    result: list[HclEntity] = list(kept_primary)
    for entity in example.entities:
        match entity:
            case TfVariable(name=n) if n in referenced_vars:
                result.append(entity)
            case TfOutput() if _output_references_kept(entity, selection):
                result.append(entity)

    return result
