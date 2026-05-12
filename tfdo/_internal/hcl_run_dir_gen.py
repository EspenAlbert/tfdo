from __future__ import annotations

from pathlib import Path

from zero_3rdparty.file_utils import ensure_parents_write_text

from tfdo._internal.hcl_entity_parser import (
    HclEntity,
    TfModuleCall,
    TfModuleExample,
    TfOutput,
    TfProvider,
    TfResource,
    TfVariable,
)
from tfdo._internal.hcl_roundtrip import (
    delete_module_block,
    delete_output_block,
    delete_provider_block,
    delete_resource_block,
    delete_variable_block,
)


def _entity_key(entity: HclEntity) -> tuple:
    if isinstance(entity, TfResource):
        return (type(entity), entity.type, entity.name)
    if isinstance(entity, TfModuleCall | TfProvider | TfVariable | TfOutput):
        return (type(entity), entity.name)
    return (type(entity),)


def _delete_entity(text: str, entity: HclEntity) -> str:
    if isinstance(entity, TfResource):
        return delete_resource_block(text, entity.type, entity.name)
    if isinstance(entity, TfModuleCall):
        return delete_module_block(text, entity.name)
    if isinstance(entity, TfProvider):
        return delete_provider_block(text, entity.name)
    if isinstance(entity, TfVariable):
        return delete_variable_block(text, entity.name)
    if isinstance(entity, TfOutput):
        return delete_output_block(text, entity.name)
    return text


def generate_run_dir(example: TfModuleExample, selected_entities: list[HclEntity], output_dir: Path) -> None:
    selected_keys = {_entity_key(e) for e in selected_entities}

    by_file: dict[Path, list[HclEntity]] = {}
    for entity in example.entities:
        by_file.setdefault(entity.file_path, []).append(entity)

    for source_file, file_entities in by_file.items():
        text = source_file.read_text()
        for entity in file_entities:
            if _entity_key(entity) not in selected_keys:
                text = _delete_entity(text, entity)
        dest = output_dir / source_file.name
        ensure_parents_write_text(dest, text)
