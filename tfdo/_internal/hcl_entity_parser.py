from __future__ import annotations

from pathlib import Path
from typing import Any

from model_lib import Event
from pydantic import Field

from tfdo._internal import hcl_compat
from tfdo._internal.hcl_roundtrip import (
    HclLiteral,
    HclValue,
    _parse_hcl_value,
    read_module_block_values,
    read_resource_block_values,
)


class TfRequiredProvider(Event):
    name: str
    source: str | None = None
    version: str | None = None


class TfVariable(Event):
    file_path: Path
    name: str
    type: HclValue | None = None
    description: str | None = None
    default: HclValue | None = None
    sensitive: bool = False
    nullable: bool | None = None


class TfOutput(Event):
    file_path: Path
    name: str
    value: HclValue
    description: str | None = None
    sensitive: bool = False


class TfResource(Event):
    file_path: Path
    type: str
    name: str
    attrs: dict[str, HclValue] = Field(default_factory=dict)

    @property
    def provider_name(self) -> str:
        return self.type.split("_")[0]


class TfModuleCall(Event):
    file_path: Path
    name: str
    source: str
    version: str | None = None
    attrs: dict[str, HclValue] = Field(default_factory=dict)


class TfRequiredProviders(Event):
    file_path: Path
    providers: list[TfRequiredProvider] = Field(default_factory=list)


class TfTerraform(Event):
    file_path: Path
    required_version: str | None = None


class TfProvider(Event):
    file_path: Path
    name: str
    alias: str | None = None
    attrs: dict[str, HclValue] = Field(default_factory=dict)


type HclEntity = TfVariable | TfOutput | TfResource | TfModuleCall | TfRequiredProviders | TfTerraform | TfProvider


class TfModuleExample(Event):
    name: str
    path: Path
    entities: list[HclEntity] = Field(default_factory=list)


_MODULE_RESERVED_ATTRS = frozenset({"source", "version"})
_PROVIDER_RESERVED_ATTRS = frozenset({"alias"})


def _parse_variables(doc: dict[str, Any], file_path: Path) -> list[TfVariable]:
    variables_list = doc.get("variable")
    if not isinstance(variables_list, list):
        return []

    entities = []
    for block in variables_list:
        if not isinstance(block, dict):
            continue
        for name, attrs in block.items():
            if not isinstance(attrs, dict):
                attrs = {}
            raw_type = attrs.get("type")
            raw_default = attrs.get("default")
            raw_nullable = attrs.get("nullable")
            entities.append(
                TfVariable(
                    file_path=file_path,
                    name=name,
                    type=_parse_hcl_value(raw_type) if raw_type is not None else None,
                    description=attrs.get("description"),
                    default=_parse_hcl_value(raw_default) if raw_default is not None else None,
                    sensitive=bool(attrs.get("sensitive", False)),
                    nullable=bool(raw_nullable) if raw_nullable is not None else None,
                )
            )
    return entities


def _parse_outputs(doc: dict[str, Any], file_path: Path) -> list[TfOutput]:
    outputs_list = doc.get("output")
    if not isinstance(outputs_list, list):
        return []

    entities = []
    for block in outputs_list:
        if not isinstance(block, dict):
            continue
        for name, attrs in block.items():
            if not isinstance(attrs, dict):
                attrs = {}
            raw_value = attrs.get("value")
            entities.append(
                TfOutput(
                    file_path=file_path,
                    name=name,
                    value=_parse_hcl_value(raw_value) if raw_value is not None else HclLiteral(None),
                    description=attrs.get("description"),
                    sensitive=bool(attrs.get("sensitive", False)),
                )
            )
    return entities


def _parse_resources(text: str, doc: dict[str, Any], file_path: Path) -> list[TfResource]:
    resources_list = doc.get("resource")
    if not isinstance(resources_list, list):
        return []

    entities = []
    for block in resources_list:
        if not isinstance(block, dict):
            continue
        for resource_type, by_name in block.items():
            if not isinstance(by_name, dict):
                continue
            for resource_name in by_name:
                attrs = read_resource_block_values(text, resource_type, resource_name)
                entities.append(
                    TfResource(
                        file_path=file_path,
                        type=resource_type,
                        name=resource_name,
                        attrs=attrs,
                    )
                )
    return entities


def _parse_module_calls(text: str, doc: dict[str, Any], file_path: Path) -> list[TfModuleCall]:
    modules_list = doc.get("module")
    if not isinstance(modules_list, list):
        return []

    entities = []
    for block in modules_list:
        if not isinstance(block, dict):
            continue
        for module_name in block:
            all_attrs = read_module_block_values(text, module_name)
            source_val = all_attrs.get("source")
            version_val = all_attrs.get("version")
            remaining = {k: v for k, v in all_attrs.items() if k not in _MODULE_RESERVED_ATTRS}

            source = source_val.value if isinstance(source_val, HclLiteral) else str(source_val)
            version = version_val.value if isinstance(version_val, HclLiteral) else None

            entities.append(
                TfModuleCall(
                    file_path=file_path,
                    name=module_name,
                    source=source,
                    version=str(version) if version is not None else None,
                    attrs=remaining,
                )
            )
    return entities


def _parse_terraform(doc: dict[str, Any], file_path: Path) -> list[TfTerraform | TfRequiredProviders]:
    terraform_list = doc.get("terraform")
    if not isinstance(terraform_list, list) or not terraform_list:
        return []

    terraform_attrs = terraform_list[0]
    if not isinstance(terraform_attrs, dict):
        return []

    entities: list[TfTerraform | TfRequiredProviders] = [
        TfTerraform(
            file_path=file_path,
            required_version=terraform_attrs.get("required_version"),
        )
    ]

    required_providers_list = terraform_attrs.get("required_providers")
    if not isinstance(required_providers_list, list) or not required_providers_list:
        return entities

    provider_block = required_providers_list[0]
    if not isinstance(provider_block, dict):
        return entities

    providers = []
    for provider_name, provider_attrs in provider_block.items():
        if not isinstance(provider_attrs, dict):
            continue
        providers.append(
            TfRequiredProvider(
                name=provider_name,
                source=provider_attrs.get("source"),
                version=provider_attrs.get("version"),
            )
        )
    entities.append(TfRequiredProviders(file_path=file_path, providers=providers))
    return entities


def _parse_providers(doc: dict[str, Any], file_path: Path) -> list[TfProvider]:
    providers_list = doc.get("provider")
    if not isinstance(providers_list, list):
        return []

    entities = []
    for block in providers_list:
        if not isinstance(block, dict):
            continue
        for provider_name, attrs in block.items():
            if not isinstance(attrs, dict):
                attrs = {}
            alias = attrs.get("alias")
            remaining = {k: _parse_hcl_value(v) for k, v in attrs.items() if k not in _PROVIDER_RESERVED_ATTRS}
            entities.append(
                TfProvider(
                    file_path=file_path,
                    name=provider_name,
                    alias=alias,
                    attrs=remaining,
                )
            )
    return entities


def parse_entities(path: Path) -> list[HclEntity]:
    text = path.read_text()
    doc = hcl_compat.hcl2_loads(text)

    entities: list[HclEntity] = []
    entities.extend(_parse_variables(doc, path))
    entities.extend(_parse_outputs(doc, path))
    entities.extend(_parse_resources(text, doc, path))
    entities.extend(_parse_module_calls(text, doc, path))
    entities.extend(_parse_terraform(doc, path))
    entities.extend(_parse_providers(doc, path))
    return entities


def parse_dir_entities(path: Path) -> list[HclEntity]:
    entities: list[HclEntity] = []
    for file in path.glob("**/*.tf"):
        entities.extend(parse_entities(file))
    return entities


def parse_module_examples(module_path: Path) -> list[TfModuleExample]:
    examples_dir = module_path / "examples"
    if not examples_dir.is_dir():
        return []
    examples = []
    for candidate in sorted(examples_dir.iterdir()):
        if not candidate.is_dir():
            continue
        tf_files = list(candidate.glob("*.tf"))
        if not tf_files:
            continue
        entities = parse_dir_entities(candidate)
        examples.append(TfModuleExample(name=candidate.name, path=candidate, entities=entities))
    return examples
