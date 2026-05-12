from __future__ import annotations

from pathlib import Path

from tfdo._internal.hcl_entity_parser import (
    TfModuleCall,
    TfOutput,
    TfProvider,
    TfRequiredProviders,
    TfResource,
    TfTerraform,
    TfVariable,
    parse_entities,
)
from tfdo._internal.hcl_roundtrip import HclAttrRef, HclLiteral, HclVarRef

_FULL_FIXTURE = """
terraform {
  required_version = ">= 1.9"
  required_providers {
    mongodbatlas = {
      source  = "mongodb/mongodbatlas"
      version = "~> 2.8"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

variable "org_id" {
  type        = string
  description = "Atlas organization ID"
  default     = "abc-123"
}

variable "sensitive_token" {
  type      = string
  sensitive = true
}

output "project_id" {
  value       = mongodbatlas_project.this.id
  description = "The project ID"
}

output "org_ref" {
  value = var.org_id
}

resource "mongodbatlas_project" "this" {
  name   = "Dev Project"
  org_id = var.org_id
}

module "alerts" {
  source     = "./modules/alerts"
  version    = "1.2.0"
  project_id = mongodbatlas_project.this.id
}

provider "random" {}

provider "aws" {
  region = "us-east-1"
  alias  = "east"
}
"""

_MINIMAL_FIXTURE = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
"""


def _write_fixture(tmp_path: Path, content: str) -> Path:
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(content)
    return tf_file


def test_parse_variables_returns_variable_entities(tmp_path: Path) -> None:
    entities = parse_entities(_write_fixture(tmp_path, _FULL_FIXTURE))
    variables = [e for e in entities if isinstance(e, TfVariable)]
    assert len(variables) == 2

    org_id = next(v for v in variables if v.name == "org_id")
    assert org_id.type == HclLiteral("string")
    assert org_id.description == "Atlas organization ID"
    assert org_id.default == HclLiteral("abc-123")
    assert not org_id.sensitive

    token = next(v for v in variables if v.name == "sensitive_token")
    assert token.sensitive
    assert token.default is None


def test_parse_outputs_returns_output_entities(tmp_path: Path) -> None:
    entities = parse_entities(_write_fixture(tmp_path, _FULL_FIXTURE))
    outputs = [e for e in entities if isinstance(e, TfOutput)]
    assert len(outputs) == 2

    project_id_out = next(o for o in outputs if o.name == "project_id")
    assert project_id_out.value == HclAttrRef("mongodbatlas_project.this.id")
    assert project_id_out.description == "The project ID"

    org_ref_out = next(o for o in outputs if o.name == "org_ref")
    assert org_ref_out.value == HclVarRef("var.org_id")


def test_parse_resources_returns_resource_entities(tmp_path: Path) -> None:
    entities = parse_entities(_write_fixture(tmp_path, _FULL_FIXTURE))
    resources = [e for e in entities if isinstance(e, TfResource)]
    assert len(resources) == 1

    res = resources[0]
    assert res.type == "mongodbatlas_project"
    assert res.name == "this"
    assert res.attrs["name"] == HclLiteral("Dev Project")
    assert res.attrs["org_id"] == HclVarRef("var.org_id")


def test_parse_module_calls_returns_module_call_entities(tmp_path: Path) -> None:
    entities = parse_entities(_write_fixture(tmp_path, _FULL_FIXTURE))
    modules = [e for e in entities if isinstance(e, TfModuleCall)]
    assert len(modules) == 1

    mod = modules[0]
    assert mod.name == "alerts"
    assert mod.source == "./modules/alerts"
    assert mod.version == "1.2.0"
    assert mod.attrs["project_id"] == HclAttrRef("mongodbatlas_project.this.id")


def test_parse_required_providers_returns_provider_entries(tmp_path: Path) -> None:
    entities = parse_entities(_write_fixture(tmp_path, _FULL_FIXTURE))
    rp_entities = [e for e in entities if isinstance(e, TfRequiredProviders)]
    assert len(rp_entities) == 1

    providers = {p.name: p for p in rp_entities[0].providers}
    assert set(providers) == {"mongodbatlas", "random"}

    atlas = providers["mongodbatlas"]
    assert atlas.source == "mongodb/mongodbatlas"
    assert atlas.version == "~> 2.8"

    random_prov = providers["random"]
    assert random_prov.source == "hashicorp/random"
    assert random_prov.version == "~> 3.0"


def test_parse_terraform_block_returns_terraform_entity(tmp_path: Path) -> None:
    entities = parse_entities(_write_fixture(tmp_path, _FULL_FIXTURE))
    tf_entities = [e for e in entities if isinstance(e, TfTerraform)]
    assert len(tf_entities) == 1
    assert tf_entities[0].required_version == ">= 1.9"


def test_parse_provider_returns_provider_entities(tmp_path: Path) -> None:
    entities = parse_entities(_write_fixture(tmp_path, _FULL_FIXTURE))
    providers = [e for e in entities if isinstance(e, TfProvider)]
    assert len(providers) == 2

    random_prov = next(p for p in providers if p.name == "random")
    assert random_prov.alias is None
    assert random_prov.attrs == {}

    aws_prov = next(p for p in providers if p.name == "aws")
    assert aws_prov.alias == "east"
    assert aws_prov.attrs["region"] == HclLiteral("us-east-1")


def test_parse_entities_returns_all_entity_types(tmp_path: Path) -> None:
    entities = parse_entities(_write_fixture(tmp_path, _FULL_FIXTURE))
    by_type = {type(e).__name__: e for e in entities}
    assert set(by_type) == {
        "TfVariable",
        "TfOutput",
        "TfResource",
        "TfModuleCall",
        "TfRequiredProviders",
        "TfTerraform",
        "TfProvider",
    }


def test_parse_entities_returns_all_entity_types_counts(tmp_path: Path) -> None:
    entities = parse_entities(_write_fixture(tmp_path, _FULL_FIXTURE))
    counts = {}
    for e in entities:
        key = type(e).__name__
        counts[key] = counts.get(key, 0) + 1
    assert counts == {
        "TfVariable": 2,
        "TfOutput": 2,
        "TfResource": 1,
        "TfModuleCall": 1,
        "TfRequiredProviders": 1,
        "TfTerraform": 1,
        "TfProvider": 2,
    }


def test_parse_terraform_without_required_version_emits_terraform_entity(tmp_path: Path) -> None:
    entities = parse_entities(_write_fixture(tmp_path, _MINIMAL_FIXTURE))
    tf_entities = [e for e in entities if isinstance(e, TfTerraform)]
    assert len(tf_entities) == 1
    assert tf_entities[0].required_version is None

    rp_entities = [e for e in entities if isinstance(e, TfRequiredProviders)]
    assert len(rp_entities) == 1
    aws = rp_entities[0].providers[0]
    assert aws.name == "aws"
    assert aws.source == "hashicorp/aws"
    assert aws.version == "~> 6.0"


def test_entity_file_path_points_to_source_file(tmp_path: Path) -> None:
    tf_file = _write_fixture(tmp_path, _FULL_FIXTURE)
    entities = parse_entities(tf_file)
    for entity in entities:
        assert entity.file_path == tf_file
