from pathlib import Path
from unittest.mock import patch

import pytest

from tfdo._internal.config.config_model import DependencyRef
from tfdo._internal.config.config_resolution import ResolvedConfig
from tfdo._internal.config.enums import TagsInject
from tfdo._internal.core import executor as executor_core
from tfdo._internal.core import terraform_init as terraform_init_core
from tfdo._internal.models import InitInput, InitMode, InitResult, OutputInput, OutputResult
from tfdo._internal.run import orchestration as orchestration_module
from tfdo._internal.run.run_context import RunDirContext
from tfdo._internal.settings import CheckConfig, TfDoSettings


def test_collect_dependency_outputs_applies_resolved_config_binary_and_tf_version(tmp_path: Path) -> None:
    captured: list[OutputInput] = []

    def fake_output(inp: OutputInput) -> OutputResult:
        captured.append(inp)
        return OutputResult(exit_code=0, outputs={"id": "out"})

    settings = TfDoSettings(work_dir=tmp_path)
    config = ResolvedConfig(
        binary="terraform",
        tf_version="1.12.1",
        backend=None,
        tags={},
        var_files=[],
        tags_inject=TagsInject.ALWAYS,
        hook_configs=[],
        dependencies=[],
        check=CheckConfig(),
    )
    run_dir = tmp_path / "envs/dev/project"
    run_dir.mkdir(parents=True)
    ctx = RunDirContext(name="project", path="envs/dev/project", repo_owner="o", repo_name="r")

    with patch.object(orchestration_module.executor, executor_core.output_json.__name__, side_effect=fake_output):
        out = orchestration_module._collect_dependency_outputs(settings, run_dir, ctx, config, InitMode.AUTO, None)

    assert out == {"id": "out"}
    assert len(captured) == 1
    assert captured[0].settings.work_dir == run_dir
    assert captured[0].settings.tf_version == "1.12.1"
    assert captured[0].settings.binary == "terraform"


@pytest.mark.parametrize(
    ("fail_stderr", "uses_reconfigure"),
    [
        ("Backend initialization required\n", False),
        ("Backend configuration changed\n", True),
    ],
)
def test_collect_dependency_outputs_auto_retries(tmp_path: Path, fail_stderr: str, uses_reconfigure: bool) -> None:
    n_out = 0
    captured_init: list[InitInput] = []

    def fake_output(_inp: OutputInput) -> OutputResult:
        nonlocal n_out
        n_out += 1
        if n_out == 1:
            return OutputResult(exit_code=1, stderr=fail_stderr)
        return OutputResult(exit_code=0, outputs={"k": "v"})

    def fake_init(inp: InitInput) -> InitResult:
        captured_init.append(inp)
        return InitResult(exit_code=0, attempts_used=1)

    settings = TfDoSettings(work_dir=tmp_path)
    config = ResolvedConfig(
        binary="terraform",
        tf_version=None,
        backend=None,
        tags={},
        var_files=[],
        tags_inject=TagsInject.ALWAYS,
        hook_configs=[],
        dependencies=[],
        check=CheckConfig(),
    )
    run_dir = tmp_path / "envs/dev/foo"
    run_dir.mkdir(parents=True)
    ctx = RunDirContext(name="foo", path="envs/dev/foo", repo_owner="o", repo_name="r")

    with (
        patch.object(orchestration_module.executor, executor_core.output_json.__name__, side_effect=fake_output),
        patch.object(orchestration_module.terraform_init, terraform_init_core.init.__name__, side_effect=fake_init),
    ):
        out = orchestration_module._collect_dependency_outputs(settings, run_dir, ctx, config, InitMode.AUTO, None)

    assert out == {"k": "v"}
    assert n_out == 2
    assert len(captured_init) == 1
    if uses_reconfigure:
        assert "-reconfigure" in captured_init[0].extra_args
    else:
        assert "-reconfigure" not in captured_init[0].extra_args


def test_resolve_dep_outputs_requires_all_keys_when_collected() -> None:
    dep = DependencyRef(ref="project", outputs={"id": "project_id"})
    assert orchestration_module._resolve_dep_outputs(dep, {}) is None
    assert orchestration_module._resolve_dep_outputs(dep, {"other": "x"}) is None


def test_resolve_dep_outputs_rejects_null_values() -> None:
    dep = DependencyRef(ref="project", outputs={"id": "project_id"})
    assert orchestration_module._resolve_dep_outputs(dep, {"id": None}) is None


def test_resolve_dep_outputs_full_collected_map() -> None:
    dep = DependencyRef(ref="project", outputs={"id": "project_id"})
    assert orchestration_module._resolve_dep_outputs(dep, {"id": "proj-1"}) == {"project_id": "proj-1"}


def test_resolve_dep_outputs_mock_requires_all_keys() -> None:
    dep = DependencyRef(
        ref="project",
        outputs={"id": "project_id"},
        outputs_mock={"id": "mock-id"},
    )
    assert orchestration_module._resolve_dep_outputs(dep, None) == {"project_id": "mock-id"}


def test_resolve_dep_outputs_mock_incomplete_returns_none() -> None:
    dep = DependencyRef(
        ref="project",
        outputs={"id": "project_id", "region": "region"},
        outputs_mock={"id": "mock-id"},
    )
    assert orchestration_module._resolve_dep_outputs(dep, None) is None
