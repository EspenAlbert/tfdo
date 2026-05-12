from __future__ import annotations

from pathlib import Path

from ask_shell.shell import run_and_wait
from zero_3rdparty.file_utils import ensure_parents_write_text

from tfdo._internal.hcl_entity_parser import (
    HclEntity,
    TfModuleCall,
    TfModuleExample,
    TfOutput,
    TfProvider,
    TfRequiredProviders,
    TfResource,
    TfVariable,
)
from tfdo._internal.hcl_entity_selector import entity_key
from tfdo._internal.hcl_roundtrip import (
    delete_module_block,
    delete_output_block,
    delete_provider_block,
    delete_resource_block,
    delete_variable_block,
    remove_required_providers,
)


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


def _prune_required_providers(text: str, file_entities: list[HclEntity], selected_provider_names: set[str]) -> str:
    for entity in file_entities:
        if not isinstance(entity, TfRequiredProviders):
            continue
        for provider in entity.providers:
            if provider.name not in selected_provider_names:
                try:
                    text = remove_required_providers(text, provider.name)
                except ValueError:
                    pass
    return text


def terraform_fmt(run_dir: Path, binary: str = "terraform") -> None:
    run_and_wait(f"{binary} fmt", cwd=run_dir)


def generate_run_dir(
    example: TfModuleExample,
    selected_entities: list[HclEntity],
    output_dir: Path,
    binary: str = "terraform",
) -> None:
    selected_keys = {entity_key(e) for e in selected_entities}
    selected_provider_names = {e.name for e in selected_entities if isinstance(e, TfProvider)} | {
        e.provider_name for e in selected_entities if isinstance(e, TfResource)
    }

    by_file: dict[Path, list[HclEntity]] = {}
    for entity in example.entities:
        by_file.setdefault(entity.file_path, []).append(entity)

    for source_file, file_entities in by_file.items():
        text = source_file.read_text()
        for entity in file_entities:
            if entity_key(entity) not in selected_keys:
                text = _delete_entity(text, entity)
        text = _prune_required_providers(text, file_entities, selected_provider_names)
        dest = output_dir / source_file.name
        ensure_parents_write_text(dest, text)

    terraform_fmt(output_dir, binary)
