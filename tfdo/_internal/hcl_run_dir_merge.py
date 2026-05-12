from __future__ import annotations

from pathlib import Path
from typing import Any

from zero_3rdparty.file_utils import ensure_parents_write_text

from tfdo._internal.hcl_entity_parser import (
    HclEntity,
    TfModuleExample,
    TfRequiredProvider,
    TfRequiredProviders,
    TfTerraform,
    parse_dir_entities,
)
from tfdo._internal.hcl_entity_selector import dedup_new_entities, entity_key
from tfdo._internal.hcl_roundtrip import delete_terraform_block, update_required_providers
from tfdo._internal.hcl_run_dir_gen import _apply_entity_edit, _delete_entity, terraform_fmt


def _new_required_providers(existing: list[HclEntity], new_entities: list[HclEntity]) -> list[TfRequiredProvider]:
    existing_names = {p.name for e in existing if isinstance(e, TfRequiredProviders) for p in e.providers}
    seen: set[str] = set()
    result: list[TfRequiredProvider] = []
    for entity in new_entities:
        if not isinstance(entity, TfRequiredProviders):
            continue
        for provider in entity.providers:
            if provider.name not in existing_names and provider.name not in seen:
                result.append(provider)
                seen.add(provider.name)
    return result


def _provider_to_attrs(provider: TfRequiredProvider) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    if provider.source is not None:
        attrs["source"] = provider.source
    if provider.version is not None:
        attrs["version"] = provider.version
    return attrs


def _find_versions_file(run_dir: Path, existing: list[HclEntity]) -> Path:
    for entity in existing:
        if isinstance(entity, TfRequiredProviders):
            return entity.file_path
    return run_dir / "versions.tf"


def _build_patch_text(source_file: Path, entities_to_add: list[HclEntity], all_file_entities: list[HclEntity]) -> str:
    """Return source file text with only entities_to_add kept (terraform block stripped)."""
    add_keys = {entity_key(e) for e in entities_to_add}
    text = source_file.read_text()
    for entity in all_file_entities:
        if entity_key(entity) not in add_keys:
            text = _delete_entity(text, entity)
    if any(isinstance(e, TfTerraform) for e in all_file_entities):
        try:
            text = delete_terraform_block(text)
        except ValueError:
            pass
    return text


def merge_run_dir(
    run_dir: Path,
    example: TfModuleExample,
    new_entities: list[HclEntity],
    original_entities: list[HclEntity] | None = None,
    binary: str = "terraform",
) -> None:
    originals = original_entities if original_entities is not None else new_entities
    orig_by_new_key = {entity_key(e): o for e, o in zip(new_entities, originals)}

    existing = parse_dir_entities(run_dir)
    deduped = dedup_new_entities(existing, new_entities)

    by_filename: dict[str, list[HclEntity]] = {}
    for entity in deduped:
        by_filename.setdefault(entity.file_path.name, []).append(entity)

    for filename, entities_to_add in by_filename.items():
        originals_to_add = [orig_by_new_key.get(entity_key(e), e) for e in entities_to_add]
        source_file = originals_to_add[0].file_path
        all_file_entities = [e for e in example.entities if e.file_path.name == filename]
        patch = _build_patch_text(source_file, originals_to_add, all_file_entities)

        for edited, original in zip(entities_to_add, originals_to_add):
            patch = _apply_entity_edit(patch, original, edited)

        dest = run_dir / filename
        if dest.exists():
            existing_text = dest.read_text()
            patch = existing_text.rstrip("\n") + "\n\n" + patch.lstrip("\n")
        ensure_parents_write_text(dest, patch)

    new_req_provs = _new_required_providers(existing, new_entities)
    if new_req_provs:
        versions_file = _find_versions_file(run_dir, existing)
        versions_text = versions_file.read_text() if versions_file.exists() else ""
        providers_dict = {p.name: _provider_to_attrs(p) for p in new_req_provs}
        updated = update_required_providers(versions_text, providers_dict)
        ensure_parents_write_text(versions_file, updated)

    terraform_fmt(run_dir, binary)
