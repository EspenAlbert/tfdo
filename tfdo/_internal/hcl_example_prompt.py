from __future__ import annotations

from ask_shell._internal.interactive import ChoiceTyped, select_list, select_list_multiple_choices

from tfdo._internal.hcl_entity_parser import (
    TfModuleCall,
    TfModuleExample,
    TfProvider,
    TfResource,
)
from tfdo._internal.hcl_entity_selector import RunDirSelection


def _block_choices(example: TfModuleExample) -> list[ChoiceTyped[tuple]]:
    choices: list[ChoiceTyped[tuple]] = []
    for entity in example.entities:
        if isinstance(entity, TfModuleCall):
            choices.append(
                ChoiceTyped(
                    name=f"module:{entity.name}",
                    value=("module", entity.name),
                    checked=True,
                )
            )
    for entity in example.entities:
        if isinstance(entity, TfResource):
            choices.append(
                ChoiceTyped(
                    name=f"resource:{entity.type}.{entity.name}",
                    value=("resource", entity.type, entity.name),
                    checked=True,
                )
            )
    for entity in example.entities:
        if isinstance(entity, TfProvider):
            choices.append(
                ChoiceTyped(
                    name=f"provider:{entity.name}",
                    value=("provider", entity.name),
                    checked=True,
                )
            )
    return choices


def _build_selection(selected_values: list[tuple]) -> RunDirSelection:
    include_resources: set[tuple[str, str]] = set()
    include_modules: set[str] = set()
    include_providers: set[str] = set()
    for item in selected_values:
        if item[0] == "module":
            include_modules.add(item[1])
        elif item[0] == "resource":
            include_resources.add((item[1], item[2]))
        elif item[0] == "provider":
            include_providers.add(item[1])
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
    default_values = [c.value for c in choices]
    selected_values = select_list_multiple_choices(
        "Select blocks to include:",
        choices,
        default=default_values,
    )
    return example, _build_selection(selected_values)
