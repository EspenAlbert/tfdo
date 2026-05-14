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
        "name": hcl_roundtrip.HclLiteral(value="Dev Project"),
        "org_id": hcl_roundtrip.HclVarRef(path="var.org_id"),
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
        "source": hcl_roundtrip.HclLiteral(value="./modules/alerts"),
        "project_id": hcl_roundtrip.HclAttrRef(path="mongodbatlas_project.this.id"),
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


def test_update_required_providers_with_required_version() -> None:
    output = hcl_roundtrip.update_required_providers(
        "",
        providers={"mongodbatlas": {"source": "mongodb/mongodbatlas", "version": "~> 2.0"}},
        required_version=">= 1.12",
    )
    assert 'required_version = ">= 1.12"' in output
    assert "mongodb/mongodbatlas" in output
    assert "required_providers {" in output


def test_update_required_providers_preserves_existing_required_version() -> None:
    fixture = """terraform {
  required_providers {
    mongodbatlas = {
      source  = "mongodb/mongodbatlas"
      version = "~> 2.8"
    }
  }
  required_version = ">= 1.10"
}
"""
    output = hcl_roundtrip.update_required_providers(
        fixture,
        providers={"aws": {"source": "hashicorp/aws"}},
    )
    assert 'required_version = ">= 1.10"' in output
    assert "hashicorp/aws" in output


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


_VERSIONS_FIXTURE = """\
terraform {
  required_providers {
    mongodbatlas = {
      source  = "mongodb/mongodbatlas"
      version = "~> 2.8"
    }
  }
  required_version = ">= 1.10"
}

# user comment preserved
provider "mongodbatlas" {}
"""

_BACKEND_ATTRS: dict[str, object] = {
    "bucket": '"my-org-tf-state"',
    "key": '"envs/dev/cluster/terraform.tfstate"',
    "region": '"us-east-1"',
    "encrypt": True,
    "use_lockfile": True,
}


def test_add_backend_block_injects_into_existing_terraform_block() -> None:
    output = hcl_roundtrip.add_backend_block(_VERSIONS_FIXTURE, "s3", _BACKEND_ATTRS)
    assert 'backend "s3" {' in output
    assert "my-org-tf-state" in output
    assert "required_providers {" in output
    assert 'required_version = ">= 1.10"' in output
    assert "# user comment preserved" in output


def test_add_backend_block_creates_terraform_block_when_absent() -> None:
    fixture = '# user-owned\nprovider "random" {}\n'
    output = hcl_roundtrip.add_backend_block(fixture, "s3", _BACKEND_ATTRS)
    assert "terraform {" in output
    assert 'backend "s3" {' in output
    assert "# user-owned" in output


def test_add_backend_block_raises_if_backend_already_exists() -> None:
    with_backend = hcl_roundtrip.add_backend_block(_VERSIONS_FIXTURE, "s3", _BACKEND_ATTRS)
    with pytest.raises(ValueError, match="backend block already exists"):
        hcl_roundtrip.add_backend_block(with_backend, "s3", _BACKEND_ATTRS)


def test_update_backend_block_replaces_config_and_preserves_other_content() -> None:
    with_backend = hcl_roundtrip.add_backend_block(_VERSIONS_FIXTURE, "s3", _BACKEND_ATTRS)
    new_attrs = {**_BACKEND_ATTRS, "bucket": '"new-bucket"'}
    output = hcl_roundtrip.update_backend_block(with_backend, "s3", new_attrs)
    assert "new-bucket" in output
    assert "my-org-tf-state" not in output
    assert "required_providers {" in output
    assert "# user comment preserved" in output


def test_update_backend_block_raises_when_no_backend_exists() -> None:
    with pytest.raises(ValueError, match="no backend block found"):
        hcl_roundtrip.update_backend_block(_VERSIONS_FIXTURE, "s3", _BACKEND_ATTRS)


def test_remove_backend_block_keeps_other_terraform_content() -> None:
    with_backend = hcl_roundtrip.add_backend_block(_VERSIONS_FIXTURE, "s3", _BACKEND_ATTRS)
    output = hcl_roundtrip.remove_backend_block(with_backend)
    assert 'backend "s3" {' not in output
    assert "required_providers {" in output
    assert "# user comment preserved" in output


def test_remove_backend_block_removes_terraform_block_when_empty() -> None:
    fixture = 'terraform {\n  backend "s3" {\n    bucket = "b"\n  }\n}\n'
    output = hcl_roundtrip.remove_backend_block(fixture)
    assert "terraform {" not in output
    assert 'backend "s3"' not in output


def test_remove_backend_block_raises_when_missing() -> None:
    with pytest.raises(ValueError, match="no backend block found"):
        hcl_roundtrip.remove_backend_block(_VERSIONS_FIXTURE)


def test_backend_round_trip_add_update_remove_is_stable() -> None:
    after_add = hcl_roundtrip.add_backend_block(_VERSIONS_FIXTURE, "s3", _BACKEND_ATTRS)
    new_attrs = {**_BACKEND_ATTRS, "bucket": '"updated-bucket"'}
    after_update = hcl_roundtrip.update_backend_block(after_add, "s3", new_attrs)
    after_remove = hcl_roundtrip.remove_backend_block(after_update)
    assert "updated-bucket" not in after_remove
    assert 'backend "s3"' not in after_remove
    assert "required_providers {" in after_remove
    assert "# user comment preserved" in after_remove


_COMPLEX_MODULE_FIXTURE = """\
module "cluster" {
  source = "../.."

  name         = "single-region"
  project_id   = var.project_id
  cluster_type = "SHARDED"
  regions = [
    {
      name          = "US_EAST_1"
      node_count    = 3
      provider_name = "AWS"
      shard_number  = 1
    }
  ]
  tags = var.tags
}

output "cluster" {
  value = module.cluster
}
"""


def test_read_module_block_values_handles_nested_list_of_objects() -> None:
    values = hcl_roundtrip.read_module_block_values(_COMPLEX_MODULE_FIXTURE, module_name="cluster")
    assert "regions" in values
    regions = values["regions"]
    assert isinstance(regions, list)
    assert len(regions) == 1
    region = regions[0]
    assert isinstance(region, dict)
    assert region["name"] == hcl_roundtrip.HclLiteral(value="US_EAST_1")
    assert region["node_count"] == hcl_roundtrip.HclLiteral(value=3)


_ATLAS_CLUSTER_MODULE_WITH_COMMENTS_FIXTURE = """\
module "cluster" {
  source = "../.."

  # Disable default production values
  auto_scaling = {
    compute_enabled = false # use manual instance_size to avoid any accidental cost
  }
  retain_backups_enabled = false # don't keep backups when deleting the cluster
  backup_enabled         = false # skip backup for dev cluster (pit_enabled auto-disables)

  cluster_type = "REPLICASET"

  # Atlas truncates cluster names to 23 characters which results in an invalid hostname due to a trailing "-" in the generated cluster name
  name       = coalesce(var.cluster_name, substr(trim(random_pet.generated_name.id, "-"), 0, 23))
  project_id = var.project_id
  regions = [
    {
      name          = "US_EAST_1" # https://www.mongodb.com/docs/atlas/cloud-providers-regions/
      node_count    = 3           # Minimum node count >= 3. Must be an odd number to support elections.
      instance_size = "M10"       # 2vCPUs and 2GB Ram
    }
  ]
  provider_name = "AWS"
  tags          = var.tags
}
"""


def test_module_attr_raw_to_patch_rhs_strips_interpolation_wrapper() -> None:
    assert hcl_roundtrip.module_attr_raw_to_patch_rhs("${var.x}") == "var.x"


def test_module_attr_raw_to_patch_rhs_serializes_list_of_objects() -> None:
    raw = [{"name": '"US_EAST_1"', "node_count": 3}]
    rhs = hcl_roundtrip.module_attr_raw_to_patch_rhs(raw)
    assert "US_EAST_1" in rhs
    assert "node_count" in rhs


def test_patch_module_block_attributes_preserves_comments_and_rewrites_source_and_name() -> None:
    output = hcl_roundtrip.patch_module_block_attributes(
        _ATLAS_CLUSTER_MODULE_WITH_COMMENTS_FIXTURE,
        module_name="cluster",
        attributes={
            "source": '"terraform-mongodbatlas-modules/cluster/mongodbatlas"',
            "name": '"my-cluster"',
        },
    )
    assert (
        'source     = "terraform-mongodbatlas-modules/cluster/mongodbatlas"' in output
        or 'source = "terraform-mongodbatlas-modules/cluster/mongodbatlas"' in output
    )
    assert 'name       = "my-cluster"' in output or 'name = "my-cluster"' in output
    assert "coalesce" not in output
    assert "../.." not in output
    assert "# Disable default production values" in output
    assert "# use manual instance_size to avoid any accidental cost" in output
    assert "# don't keep backups when deleting the cluster" in output
    assert "# skip backup for dev cluster (pit_enabled auto-disables)" in output
    assert "# Atlas truncates cluster names to 23 characters which results in an invalid hostname" in output
    assert "# https://www.mongodb.com/docs/atlas/cloud-providers-regions/" in output
    assert "# Minimum node count >= 3. Must be an odd number to support elections." in output
    assert "# 2vCPUs and 2GB Ram" in output


def test_hcl_value_str_roundtrip_nested_list_of_objects() -> None:
    from tfdo._internal.new.new_run_dir import _hcl_value_str

    values = hcl_roundtrip.read_module_block_values(_COMPLEX_MODULE_FIXTURE, module_name="cluster")
    rendered_lines = ['module "cluster" {', '  source = "../.."']
    for name, val in values.items():
        if name == "source":
            continue
        rendered_lines.append(f"  {name} = {_hcl_value_str(val)}")
    rendered_lines.append("}")
    rendered = "\n".join(rendered_lines)

    parsed = hcl2.loads(rendered)
    module_block = next(iter(parsed["module"][0].values()))
    assert module_block["regions"][0]["name"] == '"US_EAST_1"'
    assert module_block["regions"][0]["node_count"] == 3
