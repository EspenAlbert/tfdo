from __future__ import annotations

from pathlib import Path

import pytest

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
from tfdo._internal.hcl_entity_selector import (
    RunDirSelection,
    collect_var_refs,
    select_entities,
)
from tfdo._internal.hcl_roundtrip import HclAttrRef, HclLiteral, HclVarRef

_FAKE_PATH = Path("/fake/main.tf")


def _make_example(entities) -> TfModuleExample:
    return TfModuleExample(name="test", path=Path("/fake"), entities=entities)


@pytest.fixture()
def dev_cluster_example() -> TfModuleExample:
    return _make_example(
        [
            TfTerraform(file_path=_FAKE_PATH, required_version=">= 1.9"),
            TfRequiredProviders(file_path=_FAKE_PATH, providers=[]),
            TfProvider(file_path=_FAKE_PATH, name="mongodbatlas"),
            TfVariable(file_path=_FAKE_PATH, name="project_id"),
            TfVariable(file_path=_FAKE_PATH, name="tags"),
            TfVariable(file_path=_FAKE_PATH, name="cluster_name"),
            TfVariable(file_path=_FAKE_PATH, name="name_prefix"),
            TfResource(
                file_path=_FAKE_PATH,
                type="random_pet",
                name="generated_name",
                attrs={
                    "prefix": HclVarRef("var.name_prefix"),
                    "length": HclLiteral(2),
                    "keepers": {"prefix": HclVarRef("var.name_prefix")},
                },
            ),
            TfModuleCall(
                file_path=_FAKE_PATH,
                name="cluster",
                source="../..",
                attrs={
                    "name": HclAttrRef("random_pet.generated_name.id"),
                    "project_id": HclVarRef("var.project_id"),
                    "tags": HclVarRef("var.tags"),
                },
            ),
            TfOutput(file_path=_FAKE_PATH, name="cluster", value=HclAttrRef("module.cluster")),
        ]
    )


def test_from_example_selects_all_by_default(dev_cluster_example: TfModuleExample) -> None:
    selection = RunDirSelection.from_example(dev_cluster_example)
    assert ("random_pet", "generated_name") in selection.include_resources
    assert "cluster" in selection.include_modules
    assert "mongodbatlas" in selection.include_providers


def test_select_entities_includes_terraform_blocks_always(dev_cluster_example: TfModuleExample) -> None:
    selection = RunDirSelection(include_resources=set(), include_modules=set(), include_providers=set())
    result = select_entities(dev_cluster_example, selection)
    types = {type(e) for e in result}
    assert TfTerraform in types
    assert TfRequiredProviders in types


def test_select_entities_auto_includes_referenced_variables(dev_cluster_example: TfModuleExample) -> None:
    selection = RunDirSelection(
        include_resources={("random_pet", "generated_name")},
        include_modules={"cluster"},
        include_providers={"mongodbatlas"},
    )
    result = select_entities(dev_cluster_example, selection)
    var_names = {e.name for e in result if isinstance(e, TfVariable)}
    assert var_names == {"project_id", "tags", "name_prefix"}


def test_select_entities_excludes_unreferenced_variables_when_resource_dropped(
    dev_cluster_example: TfModuleExample,
) -> None:
    selection = RunDirSelection(
        include_resources=set(),
        include_modules={"cluster"},
        include_providers={"mongodbatlas"},
    )
    result = select_entities(dev_cluster_example, selection)
    var_names = {e.name for e in result if isinstance(e, TfVariable)}
    assert "cluster_name" not in var_names
    assert "name_prefix" not in var_names
    assert "project_id" in var_names
    assert "tags" in var_names


def test_collect_var_refs_from_nested_dict_and_list() -> None:
    entities: list[HclEntity] = [
        TfResource(
            file_path=_FAKE_PATH,
            type="aws_s3_bucket",
            name="this",
            attrs={
                "tags": {"env": HclVarRef("var.env"), "name": HclLiteral("foo")},
                "regions": [HclVarRef("var.region"), HclLiteral("us-east-1")],
            },
        )
    ]
    refs = collect_var_refs(entities)
    assert refs == {"env", "region"}


def test_select_entities_includes_output_referencing_kept_module(dev_cluster_example: TfModuleExample) -> None:
    selection = RunDirSelection(
        include_resources=set(),
        include_modules={"cluster"},
        include_providers={"mongodbatlas"},
    )
    result = select_entities(dev_cluster_example, selection)
    output_names = {e.name for e in result if isinstance(e, TfOutput)}
    assert "cluster" in output_names


def test_select_entities_excludes_output_when_module_not_kept(dev_cluster_example: TfModuleExample) -> None:
    selection = RunDirSelection(include_resources=set(), include_modules=set(), include_providers=set())
    result = select_entities(dev_cluster_example, selection)
    output_names = {e.name for e in result if isinstance(e, TfOutput)}
    assert output_names == set()


def test_select_entities_excludes_non_selected_provider(dev_cluster_example: TfModuleExample) -> None:
    selection = RunDirSelection(
        include_resources=set(),
        include_modules={"cluster"},
        include_providers=set(),
    )
    result = select_entities(dev_cluster_example, selection)
    providers = [e for e in result if isinstance(e, TfProvider)]
    assert providers == []
