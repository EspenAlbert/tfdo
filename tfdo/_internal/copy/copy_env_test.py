from __future__ import annotations

import filecmp
from pathlib import Path
from unittest.mock import patch

from tfdo._internal.config.config_model import TfDoConfig
from tfdo._internal.copy import copy_env as _module
from tfdo._internal.copy.copy_env import (
    CopyEnvInput,
    DstEnvExistsError,
    ModuleCallEdit,
    ResourceEdit,
    SrcEnvNotFoundError,
    copy_env,
)
from tfdo._internal.hcl_roundtrip import HclLiteral
from tfdo._internal.settings import TfDoSettings

_MODULE_TF = """\
module "atlas_project" {
  source = "mongodb/project/mongodbatlas"
  name   = "tfdo-demo-dev"
}
"""

_RESOURCE_TF = """\
resource "mongodbatlas_project" "this" {
  name   = "tfdo-demo-dev"
  org_id = "abc123"
}
"""


def _settings(tmp_path: Path) -> TfDoSettings:
    return TfDoSettings.for_testing(tmp_path, work_dir=tmp_path)


def _build_env(tmp_path: Path, env: str, run_dirs: dict[str, str]) -> None:
    base = tmp_path / "envs" / env
    for run_dir_name, content in run_dirs.items():
        tf = base / run_dir_name / "main.tf"
        tf.parent.mkdir(parents=True)
        tf.write_text(content)


def _input(tmp_path: Path, selected: list[str], **kwargs) -> CopyEnvInput:
    return CopyEnvInput(
        settings=_settings(tmp_path),
        config=TfDoConfig(),
        src_env="dev",
        dst_env="prod",
        selected_run_dirs=selected,
        **kwargs,
    )


@patch(f"{_module.__name__}.check_logic.ensure_run_dir_backend", return_value=False)
@patch(f"{_module.__name__}.terraform_fmt")
def test_pure_clone_byte_identical(mock_fmt, mock_ensure, tmp_path: Path) -> None:
    _build_env(tmp_path, "dev", {"atlas-project": _MODULE_TF, "networking": "# empty\n"})
    result = copy_env(_input(tmp_path, ["atlas-project", "networking"]))

    assert len(result.copied_run_dirs) == 2
    assert not result.edited_run_dirs
    for rd_name in ("atlas-project", "networking"):
        src = tmp_path / "envs" / "dev" / rd_name / "main.tf"
        dst = tmp_path / "envs" / "prod" / rd_name / "main.tf"
        assert filecmp.cmp(src, dst, shallow=False)

    assert mock_ensure.call_count == 2


@patch(f"{_module.__name__}.check_logic.ensure_run_dir_backend", return_value=False)
@patch(f"{_module.__name__}.terraform_fmt")
def test_deselected_run_dir_not_copied(mock_fmt, mock_ensure, tmp_path: Path) -> None:
    _build_env(tmp_path, "dev", {"keep": _MODULE_TF, "skip": _MODULE_TF})
    copy_env(_input(tmp_path, ["keep"]))

    assert (tmp_path / "envs" / "prod" / "keep").is_dir()
    assert not (tmp_path / "envs" / "prod" / "skip").exists()

    assert mock_ensure.call_count == 1


@patch(f"{_module.__name__}.check_logic.ensure_run_dir_backend", return_value=False)
@patch(f"{_module.__name__}.terraform_fmt")
def test_module_call_edit_rewrites_attr(mock_fmt, mock_ensure, tmp_path: Path) -> None:
    _build_env(tmp_path, "dev", {"atlas-project": _MODULE_TF})
    edit = ModuleCallEdit(
        run_dir="atlas-project",
        module_name="atlas_project",
        attrs={"name": HclLiteral(value="tfdo-demo-prod")},
    )
    result = copy_env(_input(tmp_path, ["atlas-project"], edits=[edit]))

    dst_tf = (tmp_path / "envs" / "prod" / "atlas-project" / "main.tf").read_text()
    assert '"tfdo-demo-prod"' in dst_tf
    assert result.edited_run_dirs == [tmp_path / "envs" / "prod" / "atlas-project"]

    assert mock_ensure.call_count == 1


@patch(f"{_module.__name__}.check_logic.ensure_run_dir_backend", return_value=False)
@patch(f"{_module.__name__}.terraform_fmt")
def test_resource_edit_rewrites_attr(mock_fmt, mock_ensure, tmp_path: Path) -> None:
    _build_env(tmp_path, "dev", {"atlas-project": _RESOURCE_TF})
    edit = ResourceEdit(
        run_dir="atlas-project",
        resource_type="mongodbatlas_project",
        resource_name="this",
        attrs={"name": HclLiteral(value="tfdo-demo-prod")},
    )
    result = copy_env(_input(tmp_path, ["atlas-project"], edits=[edit]))

    dst_tf = (tmp_path / "envs" / "prod" / "atlas-project" / "main.tf").read_text()
    assert '"tfdo-demo-prod"' in dst_tf
    assert result.edited_run_dirs == [tmp_path / "envs" / "prod" / "atlas-project"]

    assert mock_ensure.call_count == 1


def test_missing_src_env_raises(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(SrcEnvNotFoundError):
        copy_env(_input(tmp_path, []))


def test_existing_dst_env_raises(tmp_path: Path) -> None:
    import pytest

    _build_env(tmp_path, "dev", {"rd": _MODULE_TF})
    (tmp_path / "envs" / "prod").mkdir(parents=True)
    with pytest.raises(DstEnvExistsError):
        copy_env(_input(tmp_path, ["rd"]))


@patch(f"{_module.__name__}.check_logic.ensure_run_dir_backend", return_value=False)
@patch(f"{_module.__name__}.terraform_fmt")
def test_fmt_called_only_on_edited_run_dirs(mock_fmt, mock_ensure, tmp_path: Path) -> None:
    _build_env(tmp_path, "dev", {"run-a": _MODULE_TF, "run-b": _MODULE_TF})
    edit = ModuleCallEdit(
        run_dir="run-a",
        module_name="atlas_project",
        attrs={"name": HclLiteral(value="prod-name")},
    )
    result = copy_env(_input(tmp_path, ["run-a", "run-b"], edits=[edit]))

    assert mock_fmt.call_count == 1
    mock_fmt.assert_called_once_with(tmp_path / "envs" / "prod" / "run-a", "terraform")
    assert result.edited_run_dirs == [tmp_path / "envs" / "prod" / "run-a"]

    assert mock_ensure.call_count == 2
