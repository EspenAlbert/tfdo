from __future__ import annotations

import hcl2
import pytest

from tfdo._internal import hcl_roundtrip

_BASE_FIXTURE = """# tfdo managed - project
terraform {
  required_providers {
    mongodbatlas = {
      source  = "mongodb/mongodbatlas"
      version = "~> 2.8"
    }
  }
}

resource "mongodbatlas_project" "this" {
  name   = "Dev Project"
  org_id = var.org_id
}

# user-added, run-dir specific
provider "random" {}
"""


def test_read_resource_block_values_returns_hcl_value_models() -> None:
    values = hcl_roundtrip.read_resource_block_values(
        _BASE_FIXTURE,
        resource_type="mongodbatlas_project",
        resource_name="this",
    )
    assert values == {
        "name": hcl_roundtrip.HclLiteral("Dev Project"),
        "org_id": hcl_roundtrip.HclVarRef("var.org_id"),
    }


def test_read_resource_block_attrs_returns_defined_attrs() -> None:
    attrs = hcl_roundtrip.read_resource_block_attrs(
        _BASE_FIXTURE,
        resource_type="mongodbatlas_project",
        resource_name="this",
    )
    assert attrs == {
        "name": '"Dev Project"',
        "org_id": "${var.org_id}",
    }


def test_read_resource_block_attrs_raises_on_missing_block() -> None:
    with pytest.raises(ValueError, match="resource mongodbatlas_project.missing not found"):
        hcl_roundtrip.read_resource_block_attrs(
            _BASE_FIXTURE,
            resource_type="mongodbatlas_project",
            resource_name="missing",
        )


def test_update_resource_block_updates_attrs_and_preserves_canaries() -> None:
    output = hcl_roundtrip.update_resource_block(
        _BASE_FIXTURE,
        resource_type="mongodbatlas_project",
        resource_name="this",
        mutation=lambda attrs: attrs.update({"name": '"Prod Project"', "with_default_alerts_settings": False}),
    )
    assert 'name                         = "Prod Project"' in output
    assert "with_default_alerts_settings = false" in output
    assert "# tfdo managed - project" in output
    assert "# user-added, run-dir specific" in output
    assert 'provider "random" {}' in output


def test_update_resource_block_raises_on_missing_block() -> None:
    with pytest.raises(ValueError, match="resource mongodbatlas_project.missing not found"):
        hcl_roundtrip.update_resource_block(
            _BASE_FIXTURE,
            resource_type="mongodbatlas_project",
            resource_name="missing",
            mutation=lambda attrs: attrs.update({"name": '"Nope"'}),
        )


def test_update_resource_block_repeat_apply_is_stable_for_setters() -> None:
    def mutation(attrs: dict[str, object]) -> None:
        attrs.update({"name": '"Prod Project"'})

    once = hcl_roundtrip.update_resource_block(
        _BASE_FIXTURE,
        resource_type="mongodbatlas_project",
        resource_name="this",
        mutation=mutation,
    )
    twice = hcl_roundtrip.update_resource_block(
        once,
        resource_type="mongodbatlas_project",
        resource_name="this",
        mutation=mutation,
    )
    assert once == twice


def test_add_resource_block_adds_new_resource() -> None:
    output = hcl_roundtrip.add_resource_block(
        _BASE_FIXTURE,
        resource_type="mongodbatlas_project_ip_access_list",
        resource_name="office",
        attrs={
            "project_id": "mongodbatlas_project.this.id",
            "cidr_block": '"10.10.0.0/24"',
        },
    )
    assert 'resource "mongodbatlas_project_ip_access_list" "office" {' in output
    assert "project_id = mongodbatlas_project.this.id" in output
    assert "# user-added, run-dir specific" in output


def test_add_resource_block_raises_if_block_exists() -> None:
    with pytest.raises(ValueError, match="block already exists"):
        hcl_roundtrip.add_resource_block(
            _BASE_FIXTURE,
            resource_type="mongodbatlas_project",
            resource_name="this",
            attrs={"name": '"Whatever"'},
        )


def test_delete_resource_block_removes_resource_and_keeps_user_content() -> None:
    output = hcl_roundtrip.delete_resource_block(
        _BASE_FIXTURE,
        resource_type="mongodbatlas_project",
        resource_name="this",
    )
    assert 'resource "mongodbatlas_project" "this" {' not in output
    assert "# user-added, run-dir specific" in output
    assert 'provider "random" {}' in output


def test_delete_resource_block_raises_on_missing_block() -> None:
    with pytest.raises(ValueError, match="no block with labels"):
        hcl_roundtrip.delete_resource_block(
            _BASE_FIXTURE,
            resource_type="mongodbatlas_project",
            resource_name="missing",
        )


def test_add_module_block_adds_new_module() -> None:
    output = hcl_roundtrip.add_module_block(
        _BASE_FIXTURE,
        module_name="alerts",
        attrs={
            "source": '"./modules/alerts"',
            "project_id": "mongodbatlas_project.this.id",
        },
    )
    assert 'module "alerts" {' in output
    assert 'source     = "./modules/alerts"' in output
    assert "project_id = mongodbatlas_project.this.id" in output


def test_add_module_block_raises_if_block_exists() -> None:
    fixture = _BASE_FIXTURE + '\nmodule "alerts" {\n  source = "./modules/alerts"\n}\n'
    with pytest.raises(ValueError, match="block already exists"):
        hcl_roundtrip.add_module_block(
            fixture,
            module_name="alerts",
            attrs={"source": '"./modules/alerts"'},
        )


def test_delete_module_block_removes_module_and_keeps_other_content() -> None:
    fixture = hcl_roundtrip.add_module_block(
        _BASE_FIXTURE,
        module_name="alerts",
        attrs={
            "source": '"./modules/alerts"',
            "project_id": "mongodbatlas_project.this.id",
        },
    )
    output = hcl_roundtrip.delete_module_block(fixture, module_name="alerts")
    assert 'module "alerts" {' not in output
    assert 'resource "mongodbatlas_project" "this" {' in output
    assert 'provider "random" {}' in output


def test_delete_module_block_raises_on_missing_block() -> None:
    with pytest.raises(ValueError, match="no block with labels"):
        hcl_roundtrip.delete_module_block(_BASE_FIXTURE, module_name="alerts")


def test_read_module_block_attrs_returns_defined_attrs() -> None:
    fixture = hcl_roundtrip.add_module_block(
        _BASE_FIXTURE,
        module_name="alerts",
        attrs={
            "source": '"./modules/alerts"',
            "project_id": "mongodbatlas_project.this.id",
        },
    )
    attrs = hcl_roundtrip.read_module_block_attrs(fixture, module_name="alerts")
    assert attrs == {
        "source": '"./modules/alerts"',
        "project_id": "${mongodbatlas_project.this.id}",
    }


def test_read_module_block_values_returns_hcl_value_models() -> None:
    fixture = hcl_roundtrip.add_module_block(
        _BASE_FIXTURE,
        module_name="alerts",
        attrs={
            "source": '"./modules/alerts"',
            "project_id": "mongodbatlas_project.this.id",
        },
    )
    values = hcl_roundtrip.read_module_block_values(fixture, module_name="alerts")
    assert values == {
        "source": hcl_roundtrip.HclLiteral("./modules/alerts"),
        "project_id": hcl_roundtrip.HclAttrRef("mongodbatlas_project.this.id"),
    }


def test_read_module_block_attrs_raises_on_missing_block() -> None:
    with pytest.raises(ValueError, match="module alerts not found"):
        hcl_roundtrip.read_module_block_attrs(_BASE_FIXTURE, module_name="alerts")


def test_update_required_providers_updates_existing_provider() -> None:
    output = hcl_roundtrip.update_required_providers(
        _BASE_FIXTURE,
        providers={
            "mongodbatlas": {
                "version": "~> 3.0",
            },
        },
    )
    assert 'version = "~> 3.0"' in output
    assert 'source  = "mongodb/mongodbatlas"' in output


def test_update_required_providers_adds_new_provider() -> None:
    output = hcl_roundtrip.update_required_providers(
        _BASE_FIXTURE,
        providers={
            "aws": {
                "source": "hashicorp/aws",
                "version": "~> 6.0",
            },
        },
    )
    parsed = hcl2.loads(output)
    terraform = parsed["terraform"][0]
    required_providers = terraform["required_providers"][0]
    assert required_providers["aws"]["source"] == '"hashicorp/aws"'
    assert required_providers["aws"]["version"] == '"~> 6.0"'


def test_update_required_providers_keeps_non_terraform_content() -> None:
    output = hcl_roundtrip.update_required_providers(
        _BASE_FIXTURE,
        providers={"mongodbatlas": {"version": "~> 3.0"}},
    )
    assert "# user-added, run-dir specific" in output
    assert 'provider "random" {}' in output


def test_update_required_providers_creates_terraform_block_when_missing() -> None:
    fixture = '# user-owned\nprovider "random" {}\n'
    output = hcl_roundtrip.update_required_providers(
        fixture,
        providers={"aws": {"source": "hashicorp/aws", "version": "~> 6.0"}},
    )
    assert "terraform {" in output
    assert "required_providers {" in output
    assert "aws = {" in output
    assert "# user-owned" in output


def test_update_required_providers_repeat_apply_is_stable() -> None:
    once = hcl_roundtrip.update_required_providers(
        _BASE_FIXTURE,
        providers={"mongodbatlas": {"version": "~> 3.0"}},
    )
    twice = hcl_roundtrip.update_required_providers(
        once,
        providers={"mongodbatlas": {"version": "~> 3.0"}},
    )
    assert once == twice


def test_remove_required_providers_removes_only_target_provider() -> None:
    fixture = hcl_roundtrip.update_required_providers(
        _BASE_FIXTURE,
        providers={"aws": {"source": "hashicorp/aws", "version": "~> 6.0"}},
    )
    output = hcl_roundtrip.remove_required_providers(fixture, provider="aws")
    assert "hashicorp/aws" not in output
    assert "mongodb/mongodbatlas" in output
    assert "required_providers {" in output


def test_remove_required_providers_removes_section_when_last_provider_deleted() -> None:
    output = hcl_roundtrip.remove_required_providers(_BASE_FIXTURE, provider="mongodbatlas")
    assert "required_providers {" not in output
    assert "terraform {" not in output


def test_remove_required_providers_raises_when_provider_missing() -> None:
    with pytest.raises(ValueError, match="provider aws not found"):
        hcl_roundtrip.remove_required_providers(_BASE_FIXTURE, provider="aws")


def test_delete_required_providers_section_removes_entire_terraform_if_empty() -> None:
    output = hcl_roundtrip.delete_required_providers_section(_BASE_FIXTURE)
    assert "required_providers {" not in output
    assert "terraform {" not in output
    assert 'provider "random" {}' in output


def test_delete_required_providers_section_keeps_terraform_when_other_attrs_exist() -> None:
    fixture = """terraform {
  required_version = ">= 1.9"
  required_providers {
    mongodbatlas = {
      source  = "mongodb/mongodbatlas"
      version = "~> 2.8"
    }
  }
}
"""
    output = hcl_roundtrip.delete_required_providers_section(fixture)
    assert "required_providers {" not in output
    assert "terraform {" in output
    assert 'required_version = ">= 1.9"' in output


def test_delete_required_providers_section_raises_when_missing() -> None:
    fixture = '# user-owned\nprovider "random" {}\n'
    with pytest.raises(ValueError, match="required_providers section not found"):
        hcl_roundtrip.delete_required_providers_section(fixture)


_MODULE_FIXTURE = """\
module "cluster" {
  source     = "../.."
  name       = var.cluster_name
  project_id = var.project_id
}

module "other" {
  source = "../.."
  name   = "other"
}
"""


def test_rename_module_block_changes_label() -> None:
    output = hcl_roundtrip.rename_module_block(_MODULE_FIXTURE, "cluster", "cluster2")
    assert 'module "cluster2"' in output
    assert 'module "cluster"' not in output
    assert 'module "other"' in output


def test_update_module_block_mutates_attrs() -> None:
    def _set_name(attrs: dict) -> None:
        attrs["name"] = '"overridden"'

    output = hcl_roundtrip.update_module_block(_MODULE_FIXTURE, "cluster", _set_name)
    assert '"overridden"' in output
    assert "var.cluster_name" not in output
    assert 'module "other"' in output


def test_rename_resource_block_changes_label() -> None:
    fixture = """\
resource "random_pet" "prefix" {
  length = 2
}

resource "random_pet" "suffix" {
  length = 1
}
"""
    output = hcl_roundtrip.rename_resource_block(fixture, "random_pet", "prefix", "my_prefix")
    assert 'resource "random_pet" "my_prefix"' in output
    assert 'resource "random_pet" "prefix"' not in output
    assert 'resource "random_pet" "suffix"' in output
