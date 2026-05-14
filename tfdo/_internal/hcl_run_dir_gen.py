from __future__ import annotations

from pathlib import Path
from typing import Any

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
    HclAttrRef,
    HclExpression,
    HclLiteral,
    HclValue,
    HclVarRef,
    delete_module_block,
    delete_output_block,
    delete_provider_block,
    delete_resource_block,
    delete_variable_block,
    module_attr_raw_to_patch_rhs,
    patch_module_block_attributes,
    remove_required_providers,
    rename_module_block,
    rename_resource_block,
    update_module_block,
    update_resource_block,
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


def hcl_value_to_attr_raw(value: HclValue) -> Any:
    match value:
        case HclLiteral(value=v):
            return f'"{v}"' if isinstance(v, str) else v
        case HclVarRef(path=p) | HclAttrRef(path=p):
            return f"${{{p}}}"
        case HclExpression(expression=e):
            return f"${{{e}}}"
        case dict():
            return {k: hcl_value_to_attr_raw(v) for k, v in value.items()}
        case list():
            return [hcl_value_to_attr_raw(item) for item in value]
    return value


def _apply_entity_edit(text: str, original: HclEntity, edited: HclEntity) -> str:
    """Apply label rename and attr overrides from original → edited into the HCL text."""
    if original is edited:
        return text

    match (original, edited):
        case (TfModuleCall(name=orig_name, attrs=orig_attrs), TfModuleCall(name=new_name, attrs=new_attrs)):
            current_name = orig_name
            if orig_name != new_name:
                text = rename_module_block(text, orig_name, new_name)
                current_name = new_name
            changed = {k: hcl_value_to_attr_raw(v) for k, v in new_attrs.items() if orig_attrs.get(k) != v}
            if changed:
                try:
                    patch_attrs = {k: module_attr_raw_to_patch_rhs(v) for k, v in changed.items()}
                    text = patch_module_block_attributes(text, current_name, patch_attrs)
                except ValueError:
                    text = update_module_block(text, current_name, lambda a, c=changed: a.update(c))
        case (TfResource(type=t, name=orig_name, attrs=orig_attrs), TfResource(name=new_name, attrs=new_attrs)):
            current_name = orig_name
            if orig_name != new_name:
                text = rename_resource_block(text, t, orig_name, new_name)
                current_name = new_name
            changed = {k: hcl_value_to_attr_raw(v) for k, v in new_attrs.items() if orig_attrs.get(k) != v}
            if changed:
                text = update_resource_block(text, t, current_name, lambda a, c=changed: a.update(c))

    return text


def generate_run_dir(
    example: TfModuleExample,
    selected_entities: list[HclEntity],
    output_dir: Path,
    original_entities: list[HclEntity] | None = None,
    binary: str = "terraform",
) -> None:
    """Write selected entities from an example into output_dir as .tf files.

    Source files are copied with unselected blocks deleted. Pass original_entities
    when selected_entities carry field edits (label renames, attr overrides): originals
    are used for source-file block matching, and the diff between each pair is applied
    as a post-write HCL roundtrip transformation.
    """
    originals = original_entities if original_entities is not None else selected_entities
    selected_original_keys = {entity_key(o) for o in originals}
    selected_provider_names = {e.name for e in originals if isinstance(e, TfProvider)} | {
        e.provider_name for e in originals if isinstance(e, TfResource)
    }
    edit_pairs = list(zip(selected_entities, originals))

    by_file: dict[Path, list[HclEntity]] = {}
    for entity in example.entities:
        by_file.setdefault(entity.file_path, []).append(entity)

    for source_file, file_entities in by_file.items():
        text = source_file.read_text()
        for entity in file_entities:
            if entity_key(entity) not in selected_original_keys:
                text = _delete_entity(text, entity)
        text = _prune_required_providers(text, file_entities, selected_provider_names)
        for edited, original in edit_pairs:
            if original.file_path == source_file:
                text = _apply_entity_edit(text, original, edited)
        dest = output_dir / source_file.name
        ensure_parents_write_text(dest, text)

    terraform_fmt(output_dir, binary)
