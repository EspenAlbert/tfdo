from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ask_shell._internal.interactive import ChoiceTyped, select_list, select_list_multiple_choices, text

from tfdo._internal.hcl_entity_parser import (
    HclEntity,
    TfModuleCall,
    TfModuleExample,
    TfProvider,
    TfResource,
    parse_dir_entities,
)
from tfdo._internal.hcl_entity_selector import RunDirSelection, entity_key
from tfdo._internal.hcl_roundtrip import HclAttrRef, HclExpression, HclLiteral, HclValue, HclVarRef


@dataclass(frozen=True)
class EditableField:
    entity_idx: int
    field: str
    display: str
    current: str


def _hcl_value_display(value: HclValue) -> str:
    match value:
        case HclLiteral(value=v):
            return repr(v) if isinstance(v, str) else str(v)
        case HclVarRef(path=p):
            return f"${{{p}}}"
        case HclAttrRef(path=p):
            return p
        case HclExpression(expression=e):
            return e
        case dict():
            return "{...}"
        case list():
            return "[...]"
    return str(value)


def _editable_fields(entity: HclEntity, idx: int) -> list[EditableField]:
    match entity:
        case TfModuleCall(name=n, attrs=attrs):
            entity_ref = f"module:{n}"
            fields = [EditableField(idx, "label", f"{entity_ref}  [label]", n)]
            for key, value in attrs.items():
                if isinstance(value, dict | list):
                    continue
                cur = _hcl_value_display(value)
                fields.append(EditableField(idx, key, f"{entity_ref}.{key} = {cur}", cur))
            return fields
        case TfResource(type=t, name=n, attrs=attrs):
            entity_ref = f"resource:{t}.{n}"
            fields = [EditableField(idx, "label", f"{entity_ref}  [label]", n)]
            for key, value in attrs.items():
                if isinstance(value, dict | list):
                    continue
                cur = _hcl_value_display(value)
                fields.append(EditableField(idx, key, f"{entity_ref}.{key} = {cur}", cur))
            return fields
    return []


_VAR_REF_PREFIXES = ("var.", "local.")
_ATTR_REF_PREFIXES = ("module.", "resource.", "data.", "path.", "each.", "count.")


def _strip_quotes(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == '"' and stripped[-1] == '"':
        return stripped[1:-1]
    return stripped


def _parse_user_hcl_value(raw: str) -> HclValue:
    """Parse a user-typed string into the appropriate HclValue.

    Rules (checked in order):
    - "${...}"          → HclExpression
    - var.* / local.*  → HclVarRef
    - module.* / …     → HclAttrRef
    - "quoted"         → HclLiteral with inner value (strips surrounding quotes)
    - anything else    → HclLiteral as-is
    """
    stripped = raw.strip()
    if stripped.startswith("${") and stripped.endswith("}"):
        return HclExpression(stripped[2:-1])
    if any(stripped.startswith(p) for p in _VAR_REF_PREFIXES):
        return HclVarRef(stripped)
    if any(stripped.startswith(p) for p in _ATTR_REF_PREFIXES):
        return HclAttrRef(stripped)
    return HclLiteral(_strip_quotes(stripped))


def _apply_field_edit(entity: HclEntity, field: str, new_value: str) -> HclEntity:
    if field == "label":
        return entity.model_copy(update={"name": _strip_quotes(new_value)})
    parsed: HclValue = _parse_user_hcl_value(new_value)
    match entity:
        case TfModuleCall(attrs=attrs):
            return entity.model_copy(update={"attrs": {**attrs, field: parsed}})
        case TfResource(attrs=attrs):
            return entity.model_copy(update={"attrs": {**attrs, field: parsed}})
    return entity


def ask_field_edits(entities: list[HclEntity]) -> tuple[list[HclEntity], list[HclEntity]]:
    """Interactively rename labels or override attribute values on selected entities.

    Returns (edited_entities, original_entities). The originals are needed by
    merge_run_dir / generate_run_dir for source-file block matching, while edited
    entities carry the new labels used for dedup and display.
    """
    all_fields: list[EditableField] = []
    for idx, entity in enumerate(entities):
        all_fields.extend(_editable_fields(entity, idx))

    if not all_fields:
        return list(entities), list(entities)

    choices = [ChoiceTyped(name=f.display, value=f, checked=False) for f in all_fields]
    selected_fields = select_list_multiple_choices(
        "Select fields to edit (none = skip):",
        choices,
        default=[],
    )

    if not selected_fields:
        return list(entities), list(entities)

    edits_by_entity: dict[int, list[tuple[str, str]]] = {}
    for field_edit in selected_fields:
        new_val = text(f"  {field_edit.display}", default=field_edit.current)
        edits_by_entity.setdefault(field_edit.entity_idx, []).append((field_edit.field, new_val))

    originals = list(entities)
    edited = list(entities)
    for entity_idx, field_edits in edits_by_entity.items():
        entity = edited[entity_idx]
        for field, new_value in field_edits:
            entity = _apply_field_edit(entity, field, new_value)
        edited[entity_idx] = entity
    return edited, originals


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
