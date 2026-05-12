from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ask_shell._internal.interactive import ChoiceTyped, select_list, select_list_multiple_choices

from tfdo._internal.hcl_entity_parser import (
    TfModuleCall,
    TfModuleExample,
    TfProvider,
    TfResource,
    parse_dir_entities,
)
from tfdo._internal.hcl_entity_selector import RunDirSelection, entity_key


@dataclass(frozen=True)
class ModuleBlock:
    name: str

    def label(self) -> str:
        return f"module:{self.name}"


@dataclass(frozen=True)
class ResourceBlock:
    type: str
    name: str

    def label(self) -> str:
        return f"resource:{self.type}.{self.name}"


@dataclass(frozen=True)
class ProviderBlock:
    name: str

    def label(self) -> str:
        return f"provider:{self.name}"


type BlockChoice = ModuleBlock | ResourceBlock | ProviderBlock


def _block_choices(example: TfModuleExample, existing_keys: set[tuple] | None = None) -> list[ChoiceTyped[BlockChoice]]:
    existing_keys = existing_keys or set()
    choices: list[ChoiceTyped[BlockChoice]] = []
    for entity in example.entities:
        if isinstance(entity, TfModuleCall):
            block = ModuleBlock(name=entity.name)
            choices.append(
                ChoiceTyped(name=block.label(), value=block, checked=entity_key(entity) not in existing_keys)
            )
    for entity in example.entities:
        if isinstance(entity, TfResource):
            block = ResourceBlock(type=entity.type, name=entity.name)
            choices.append(
                ChoiceTyped(name=block.label(), value=block, checked=entity_key(entity) not in existing_keys)
            )
    for entity in example.entities:
        if isinstance(entity, TfProvider):
            block = ProviderBlock(name=entity.name)
            choices.append(
                ChoiceTyped(name=block.label(), value=block, checked=entity_key(entity) not in existing_keys)
            )
    return choices


def _build_selection(selected: list[BlockChoice]) -> RunDirSelection:
    include_resources: set[tuple[str, str]] = set()
    include_modules: set[str] = set()
    include_providers: set[str] = set()
    for block in selected:
        if isinstance(block, ModuleBlock):
            include_modules.add(block.name)
        elif isinstance(block, ResourceBlock):
            include_resources.add((block.type, block.name))
        elif isinstance(block, ProviderBlock):
            include_providers.add(block.name)
    return RunDirSelection(
        include_resources=include_resources,
        include_modules=include_modules,
        include_providers=include_providers,
    )


def ask_example_selection(examples: list[TfModuleExample]) -> tuple[TfModuleExample, RunDirSelection]:
    example_names = [ex.name for ex in examples]
    chosen_name = select_list("Which example?", example_names, default=example_names[0])
    example = next(ex for ex in examples if ex.name == chosen_name)

    choices = _block_choices(example)
    selected = select_list_multiple_choices(
        "Select blocks to include:",
        choices,
        default=[c.value for c in choices],
    )
    return example, _build_selection(selected)


def ask_merge_selection(run_dir: Path, examples: list[TfModuleExample]) -> tuple[TfModuleExample, RunDirSelection]:
    existing_entities = parse_dir_entities(run_dir)
    existing_keys = {entity_key(e) for e in existing_entities}

    example_names = [ex.name for ex in examples]
    chosen_name = select_list("Which example to merge from?", example_names, default=example_names[0])
    example = next(ex for ex in examples if ex.name == chosen_name)

    choices = _block_choices(example, existing_keys=existing_keys)
    selected = select_list_multiple_choices(
        "Select blocks to add (unchecked = already exists in run-dir):",
        choices,
        default=[c.value for c in choices if c.checked],
    )
    return example, _build_selection(selected)
