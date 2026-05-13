from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from tfdo._internal.config.config_model import TfDoConfig
from tfdo._internal.config.env_var_loader import LoadResult
from tfdo._internal.config.resolver import ResolvedProvider, ResolvedRunDirConfig
from tfdo._internal.hcl_roundtrip import HclLiteral, HclVarRef
from tfdo._internal.new import new_run_dir as _module
from tfdo._internal.new.new_run_dir import (
    AttrPromotion,
    ModuleRunDirConfig,
    NewRunDirInput,
    new_run_dir,
)
from tfdo._internal.settings import TfDoSettings

_EMPTY_RESOLVED = ResolvedRunDirConfig(
    required_providers=[],
    resolved_modules=[],
    provider_hints={},
    auth_variables=[],
    loaded_env_vars=LoadResult(merged={}, loaded_paths=[], reason="skip"),
)


def _settings(tmp_path: Path) -> TfDoSettings:
    return TfDoSettings.for_testing(tmp_path, work_dir=tmp_path)


def _input(tmp_path: Path, **kwargs) -> NewRunDirInput:
    return NewRunDirInput(
        settings=_settings(tmp_path),
        config=TfDoConfig(),
        env_name="dev",
        run_dir_name="cluster",
        **kwargs,
    )


@patch(f"{_module.__name__}.terraform_fmt")
@patch(f"{_module.__name__}.resolve_run_dir", return_value=_EMPTY_RESOLVED)
def test_tf_var_promotion_writes_variable_and_tfvars(mock_resolve, mock_fmt, tmp_path: Path) -> None:
    promotion = AttrPromotion(attr_name="org_id", tf_var_name="org_id", default_value="my-org")
    cfg = ModuleRunDirConfig(
        source="ns/project/mongodbatlas",
        label="project",
        attrs={"org_id": HclVarRef("var.org_id")},
        tf_var_promotions=[promotion],
    )
    result = new_run_dir(_input(tmp_path, module_configs=[cfg]))

    variables_tf = (result.run_dir / "variables.tf").read_text()
    assert 'variable "org_id"' in variables_tf
    assert "type = string" in variables_tf

    tfvars = (result.run_dir / "terraform.tfvars").read_text()
    assert 'org_id = "my-org"' in tfvars

    main_tf = (result.run_dir / "main.tf").read_text()
    assert "var.org_id" in main_tf


@patch(f"{_module.__name__}.terraform_fmt")
@patch(f"{_module.__name__}.resolve_run_dir", return_value=_EMPTY_RESOLVED)
def test_literal_attr_in_main_tf_no_variables_file(mock_resolve, mock_fmt, tmp_path: Path) -> None:
    cfg = ModuleRunDirConfig(
        source="ns/project/mongodbatlas",
        label="project",
        attrs={"name": HclLiteral("tfdo-demo")},
    )
    result = new_run_dir(_input(tmp_path, module_configs=[cfg]))

    main_tf = (result.run_dir / "main.tf").read_text()
    assert 'name = "tfdo-demo"' in main_tf
    assert not (result.run_dir / "variables.tf").exists()
    assert not (result.run_dir / "terraform.tfvars").exists()


@patch(f"{_module.__name__}.terraform_fmt")
@patch(f"{_module.__name__}.resolve_run_dir", return_value=_EMPTY_RESOLVED)
def test_outputs_written_for_exposed(mock_resolve, mock_fmt, tmp_path: Path) -> None:
    cfg = ModuleRunDirConfig(
        source="ns/project/mongodbatlas",
        label="project",
        exposed_outputs=["id", "project_id"],
    )
    result = new_run_dir(_input(tmp_path, module_configs=[cfg]))

    outputs_tf = (result.run_dir / "outputs.tf").read_text()
    assert 'output "id"' in outputs_tf
    assert "module.project.id" in outputs_tf
    assert 'output "project_id"' in outputs_tf


@patch(f"{_module.__name__}.terraform_fmt")
@patch(f"{_module.__name__}.resolve_run_dir")
def test_resolver_result_lands_in_versions_tf(mock_resolve, mock_fmt, tmp_path: Path) -> None:
    resolved = ResolvedRunDirConfig(
        required_providers=[ResolvedProvider(name="mongodbatlas", source="mongodb/mongodbatlas", constraint="~> 2.0")],
        resolved_modules=[],
        provider_hints={},
        auth_variables=[],
        loaded_env_vars=LoadResult(merged={}, loaded_paths=[], reason="skip"),
    )
    mock_resolve.return_value = resolved

    result = new_run_dir(_input(tmp_path))

    versions_tf = (result.run_dir / "versions.tf").read_text()
    assert "mongodbatlas" in versions_tf
    assert "mongodb/mongodbatlas" in versions_tf


@patch(f"{_module.__name__}.terraform_fmt")
@patch(f"{_module.__name__}.resolve_run_dir", return_value=_EMPTY_RESOLVED)
def test_no_terraform_dir_under_run_dir(mock_resolve, mock_fmt, tmp_path: Path) -> None:
    result = new_run_dir(_input(tmp_path))
    assert not (result.run_dir / ".terraform").exists()
