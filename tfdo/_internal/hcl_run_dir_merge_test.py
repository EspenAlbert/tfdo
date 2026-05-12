from __future__ import annotations

from pathlib import Path

from tfdo._internal.hcl_entity_parser import TfModuleCall, parse_module_examples
from tfdo._internal.hcl_entity_selector import RunDirSelection, select_entities
from tfdo._internal.hcl_roundtrip import HclLiteral
from tfdo._internal.hcl_run_dir_gen import generate_run_dir
from tfdo._internal.hcl_run_dir_merge import merge_run_dir

# --- shared fixture content ---

_ATLAS_MAIN_TF = """\
module "cluster" {
  source     = "../.."
  name       = var.cluster_name
  project_id = var.project_id
}

output "cluster" {
  value = module.cluster
}
"""

_ATLAS_VARIABLES_TF = """\
variable "project_id" {
  type = string
}

variable "cluster_name" {
  type    = string
  default = "my-cluster"
}
"""

_ATLAS_VERSIONS_TF = """\
terraform {
  required_providers {
    mongodbatlas = {
      source  = "mongodb/mongodbatlas"
      version = "~> 2.0"
    }
  }
  required_version = ">= 1.9"
}

provider "mongodbatlas" {}
"""

# A second example that adds a random_pet resource (new provider required)
_RANDOM_MAIN_TF = """\
resource "random_pet" "prefix" {
  length = 2
}

module "cluster" {
  source     = "../.."
  name       = random_pet.prefix.id
  project_id = var.project_id
}
"""

_RANDOM_VARIABLES_TF = """\
variable "project_id" {
  type = string
}
"""

_RANDOM_VERSIONS_TF = """\
terraform {
  required_providers {
    mongodbatlas = {
      source  = "mongodb/mongodbatlas"
      version = "~> 2.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.0"
    }
  }
  required_version = ">= 1.9"
}
"""


def _write_atlas_example(tmp_path: Path) -> Path:
    example_dir = tmp_path / "atlas_module" / "examples" / "basic"
    example_dir.mkdir(parents=True)
    (example_dir / "main.tf").write_text(_ATLAS_MAIN_TF)
    (example_dir / "variables.tf").write_text(_ATLAS_VARIABLES_TF)
    (example_dir / "versions.tf").write_text(_ATLAS_VERSIONS_TF)
    return tmp_path / "atlas_module"


def _write_random_example(tmp_path: Path) -> Path:
    example_dir = tmp_path / "random_module" / "examples" / "with_random"
    example_dir.mkdir(parents=True)
    (example_dir / "main.tf").write_text(_RANDOM_MAIN_TF)
    (example_dir / "variables.tf").write_text(_RANDOM_VARIABLES_TF)
    (example_dir / "versions.tf").write_text(_RANDOM_VERSIONS_TF)
    return tmp_path / "random_module"


def _make_run_dir_from_atlas(tmp_path: Path) -> Path:
    atlas_module = _write_atlas_example(tmp_path)
    examples = parse_module_examples(atlas_module)
    example = examples[0]
    selection = RunDirSelection.from_example(example)
    selected = select_entities(example, selection)
    run_dir = tmp_path / "run_dir"
    generate_run_dir(example, selected, run_dir)
    return run_dir


def test_merge_adds_new_module_not_in_run_dir(tmp_path: Path) -> None:
    run_dir = _make_run_dir_from_atlas(tmp_path)
    random_module = _write_random_example(tmp_path)
    examples = parse_module_examples(random_module)
    example = examples[0]

    # Select only the random_pet resource (module "cluster" already exists)
    selection = RunDirSelection(
        include_resources={("random_pet", "prefix")},
        include_modules=set(),
        include_providers=set(),
    )
    new_entities = select_entities(example, selection)
    merge_run_dir(run_dir, example, new_entities)

    main_out = (run_dir / "main.tf").read_text()
    assert 'resource "random_pet" "prefix"' in main_out
    assert main_out.count('module "cluster"') == 1


def test_merge_does_not_duplicate_existing_module(tmp_path: Path) -> None:
    run_dir = _make_run_dir_from_atlas(tmp_path)
    random_module = _write_random_example(tmp_path)
    examples = parse_module_examples(random_module)
    example = examples[0]

    # Try to merge module "cluster" which already exists in run_dir
    selection = RunDirSelection(
        include_resources=set(),
        include_modules={"cluster"},
        include_providers=set(),
    )
    new_entities = select_entities(example, selection)
    merge_run_dir(run_dir, example, new_entities)

    main_out = (run_dir / "main.tf").read_text()
    assert main_out.count('module "cluster"') == 1


def test_merge_does_not_duplicate_existing_variable(tmp_path: Path) -> None:
    run_dir = _make_run_dir_from_atlas(tmp_path)
    random_module = _write_random_example(tmp_path)
    examples = parse_module_examples(random_module)
    example = examples[0]

    # random module also uses project_id variable which already exists in run_dir
    selection = RunDirSelection(
        include_resources={("random_pet", "prefix")},
        include_modules=set(),
        include_providers=set(),
    )
    new_entities = select_entities(example, selection)
    merge_run_dir(run_dir, example, new_entities)

    vars_out = (run_dir / "variables.tf").read_text()
    assert vars_out.count('variable "project_id"') == 1


def test_merge_adds_new_required_provider(tmp_path: Path) -> None:
    run_dir = _make_run_dir_from_atlas(tmp_path)
    random_module = _write_random_example(tmp_path)
    examples = parse_module_examples(random_module)
    example = examples[0]

    selection = RunDirSelection(
        include_resources={("random_pet", "prefix")},
        include_modules=set(),
        include_providers=set(),
    )
    new_entities = select_entities(example, selection)
    merge_run_dir(run_dir, example, new_entities)

    versions_out = (run_dir / "versions.tf").read_text()
    assert "mongodbatlas" in versions_out
    assert "random" in versions_out
    assert versions_out.count("terraform {") == 1


def test_merge_does_not_duplicate_existing_required_provider(tmp_path: Path) -> None:
    run_dir = _make_run_dir_from_atlas(tmp_path)
    random_module = _write_random_example(tmp_path)
    examples = parse_module_examples(random_module)
    example = examples[0]

    selection = RunDirSelection.from_example(example)
    new_entities = select_entities(example, selection)
    merge_run_dir(run_dir, example, new_entities)

    versions_out = (run_dir / "versions.tf").read_text()
    assert versions_out.count('"mongodb/mongodbatlas"') == 1


def test_merge_into_empty_dir_behaves_like_generate(tmp_path: Path) -> None:
    atlas_module = _write_atlas_example(tmp_path)
    examples = parse_module_examples(atlas_module)
    example = examples[0]
    selection = RunDirSelection.from_example(example)
    new_entities = select_entities(example, selection)

    empty_run_dir = tmp_path / "empty_run_dir"
    empty_run_dir.mkdir()
    merge_run_dir(empty_run_dir, example, new_entities)

    main_out = (empty_run_dir / "main.tf").read_text()
    vars_out = (empty_run_dir / "variables.tf").read_text()
    assert 'module "cluster"' in main_out
    assert 'variable "project_id"' in vars_out


def test_merge_with_label_rename_writes_renamed_block(tmp_path: Path) -> None:
    run_dir = _make_run_dir_from_atlas(tmp_path)
    random_module = _write_random_example(tmp_path)
    examples = parse_module_examples(random_module)
    example = examples[0]

    selection = RunDirSelection(
        include_resources=set(),
        include_modules={"cluster"},
        include_providers=set(),
    )
    originals = select_entities(example, selection)
    edited = [
        e.model_copy(update={"name": "cluster2"}) if isinstance(e, TfModuleCall) and e.name == "cluster" else e
        for e in originals
    ]

    merge_run_dir(run_dir, example, edited, original_entities=originals)

    main_out = (run_dir / "main.tf").read_text()
    assert 'module "cluster"' in main_out
    assert 'module "cluster2"' in main_out


def test_merge_with_attr_override_writes_literal_value(tmp_path: Path) -> None:
    atlas_module = _write_atlas_example(tmp_path)
    examples = parse_module_examples(atlas_module)
    example = examples[0]
    selection = RunDirSelection(
        include_resources=set(),
        include_modules={"cluster"},
        include_providers=set(),
    )
    originals = select_entities(example, selection)
    edited = [
        e.model_copy(update={"attrs": {**e.attrs, "name": HclLiteral("my-hardcoded-name")}})
        if isinstance(e, TfModuleCall) and e.name == "cluster"
        else e
        for e in originals
    ]

    run_dir = tmp_path / "run_dir"
    run_dir.mkdir()
    merge_run_dir(run_dir, example, edited, original_entities=originals)

    main_out = (run_dir / "main.tf").read_text()
    assert "my-hardcoded-name" in main_out
    assert "var.cluster_name" not in main_out
