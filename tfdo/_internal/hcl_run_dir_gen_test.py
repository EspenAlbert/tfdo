from __future__ import annotations

from pathlib import Path

from tfdo._internal.hcl_entity_parser import parse_module_examples
from tfdo._internal.hcl_entity_selector import RunDirSelection, select_entities
from tfdo._internal.hcl_run_dir_gen import generate_run_dir

_MAIN_TF = """\
resource "random_pet" "generated_name" {
  prefix = var.name_prefix
  length = 2
}

module "cluster" {
  source     = "../.."
  name       = random_pet.generated_name.id
  project_id = var.project_id
  tags       = var.tags
}

output "cluster" {
  value = module.cluster
}
"""

_VARIABLES_TF = """\
variable "project_id" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "name_prefix" {
  type    = string
  default = "dev-"
}
"""

_VERSIONS_TF = """\
terraform {
  required_providers {
    mongodbatlas = {
      source  = "mongodb/mongodbatlas"
      version = "~> 2.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 2.0"
    }
  }
  required_version = ">= 1.9"
}

provider "mongodbatlas" {}
"""


def _write_example(tmp_path: Path) -> Path:
    example_dir = tmp_path / "examples" / "08_dev"
    example_dir.mkdir(parents=True)
    (example_dir / "main.tf").write_text(_MAIN_TF)
    (example_dir / "variables.tf").write_text(_VARIABLES_TF)
    (example_dir / "versions.tf").write_text(_VERSIONS_TF)
    return tmp_path


def test_generate_run_dir_omits_deselected_resource(tmp_path: Path) -> None:
    module_path = _write_example(tmp_path)
    examples = parse_module_examples(module_path)
    assert len(examples) == 1
    example = examples[0]

    selection = RunDirSelection(
        include_resources=set(),
        include_modules={"cluster"},
        include_providers={"mongodbatlas"},
    )
    selected = select_entities(example, selection)
    out = tmp_path / "run_dir"
    generate_run_dir(example, selected, out)

    main_out = (out / "main.tf").read_text()
    assert 'resource "random_pet"' not in main_out
    assert 'module "cluster"' in main_out
    assert 'output "cluster"' in main_out


def test_generate_run_dir_omits_unreferenced_variable(tmp_path: Path) -> None:
    module_path = _write_example(tmp_path)
    examples = parse_module_examples(module_path)
    example = examples[0]

    selection = RunDirSelection(
        include_resources=set(),
        include_modules={"cluster"},
        include_providers={"mongodbatlas"},
    )
    selected = select_entities(example, selection)
    out = tmp_path / "run_dir"
    generate_run_dir(example, selected, out)

    vars_out = (out / "variables.tf").read_text()
    assert "name_prefix" not in vars_out
    assert "project_id" in vars_out
    assert "tags" in vars_out


def test_generate_run_dir_keeps_all_when_full_selection(tmp_path: Path) -> None:
    module_path = _write_example(tmp_path)
    examples = parse_module_examples(module_path)
    example = examples[0]

    selection = RunDirSelection.from_example(example)
    selected = select_entities(example, selection)
    out = tmp_path / "run_dir"
    generate_run_dir(example, selected, out)

    main_out = (out / "main.tf").read_text()
    vars_out = (out / "variables.tf").read_text()
    assert 'resource "random_pet"' in main_out
    assert 'module "cluster"' in main_out
    assert "name_prefix" in vars_out
    assert "project_id" in vars_out


def test_generate_run_dir_preserves_versions_tf(tmp_path: Path) -> None:
    module_path = _write_example(tmp_path)
    examples = parse_module_examples(module_path)
    example = examples[0]

    selection = RunDirSelection.from_example(example)
    selected = select_entities(example, selection)
    out = tmp_path / "run_dir"
    generate_run_dir(example, selected, out)

    versions_out = (out / "versions.tf").read_text()
    assert "mongodbatlas" in versions_out
    assert "required_version" in versions_out


def test_generate_run_dir_keeps_required_provider_implied_by_selected_resource(tmp_path: Path) -> None:
    # random_pet resource is selected but there is no provider "random" {} block.
    # The required_providers entry for random must be kept because the resource implies it.
    module_path = _write_example(tmp_path)
    examples = parse_module_examples(module_path)
    example = examples[0]

    selection = RunDirSelection(
        include_resources={("random_pet", "generated_name")},
        include_modules={"cluster"},
        include_providers={"mongodbatlas"},
    )
    selected = select_entities(example, selection)
    out = tmp_path / "run_dir"
    generate_run_dir(example, selected, out)

    versions_out = (out / "versions.tf").read_text()
    assert "mongodbatlas" in versions_out
    assert "random" in versions_out


def test_generate_run_dir_prunes_unused_required_provider(tmp_path: Path) -> None:
    module_path = _write_example(tmp_path)
    examples = parse_module_examples(module_path)
    example = examples[0]

    # deselect the random_pet resource → random provider no longer needed
    selection = RunDirSelection(
        include_resources=set(),
        include_modules={"cluster"},
        include_providers={"mongodbatlas"},
    )
    selected = select_entities(example, selection)
    out = tmp_path / "run_dir"
    generate_run_dir(example, selected, out)

    versions_out = (out / "versions.tf").read_text()
    assert "mongodbatlas" in versions_out
    assert "random" not in versions_out


def test_parse_module_examples_finds_example_dirs(tmp_path: Path) -> None:
    module_path = _write_example(tmp_path)
    examples = parse_module_examples(module_path)
    assert len(examples) == 1
    assert examples[0].name == "08_dev"
    assert any(e.__class__.__name__ == "TfModuleCall" for e in examples[0].entities)
