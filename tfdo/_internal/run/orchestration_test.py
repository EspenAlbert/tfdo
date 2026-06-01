from pathlib import Path
from unittest.mock import patch

import pytest

from tfdo._internal.config.config_model import DependencyRef
from tfdo._internal.config.config_resolution import ResolvedConfig
from tfdo._internal.config.enums import LifecycleCommand, TagsInject
from tfdo._internal.core import executor as executor_core
from tfdo._internal.core import terraform_init as terraform_init_core
from tfdo._internal.models import ApplyResult, InitInput, InitMode, InitResult, OutputInput, OutputResult, PlanResult
from tfdo._internal.run import orchestration as orchestration_module
from tfdo._internal.run.run_context import RunDirContext
from tfdo._internal.run.run_dir_summary import FAILURE_LABEL, ResourceActionCounts
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


def test_run_dir_result_attaches_plan_summary() -> None:
    counts = ResourceActionCounts(add=1, change=0, destroy=0, replace=0)
    outcome = orchestration_module._DispatchOutcome(0, False, "", "", counts, 2, True)
    result = orchestration_module._run_dir_result("envs/dev/app", LifecycleCommand.PLAN, outcome, duration_s=1.2)
    assert result.summary is not None
    assert result.summary.duration_s == 1.2
    assert result.summary.resource_counts == counts
    assert result.summary.output_change_count == 2
    assert result.summary.has_applyable_changes is True


def test_skipped_run_dir_result_has_summary() -> None:
    result = orchestration_module._skipped_run_dir_result("envs/dev/app", LifecycleCommand.APPLY, 1)
    assert result.skipped
    assert result.summary is not None
    assert result.summary.command == "apply"
    assert result.summary.exit_code == 1


def test_outcome_from_plan_maps_counts() -> None:
    plan_result = PlanResult(
        exit_code=0,
        resource_counts=ResourceActionCounts(add=2, change=1, destroy=0, replace=0),
        output_change_count=1,
        has_applyable_changes=True,
    )
    outcome = orchestration_module._outcome_from_plan(plan_result)
    assert outcome.resource_counts is not None
    assert outcome.resource_counts.add == 2
    assert outcome.output_change_count == 1


def _minimal_resolved_config() -> ResolvedConfig:
    return ResolvedConfig(
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


def test_execute_run_dir_attaches_summary(tmp_path: Path) -> None:
    settings = TfDoSettings(work_dir=tmp_path)
    config = _minimal_resolved_config()
    ctx = RunDirContext(name="app", path="envs/dev/app", repo_owner="o", repo_name="r")
    inp = orchestration_module.RunOrchestrationInput(settings=settings, command=LifecycleCommand.PLAN)
    prepared = orchestration_module.PreparedRunDir(
        init_input=InitInput(settings=settings),
        lifecycle_flags=[],
    )
    counts = ResourceActionCounts(add=1, change=0, destroy=0, replace=0)

    def fake_dispatch(*_args: object, **_kwargs: object) -> orchestration_module._DispatchOutcome:
        return orchestration_module._DispatchOutcome(0, False, "", "", counts, None, True)

    with (
        patch.object(orchestration_module, "prepare_run_dir", return_value=prepared),
        patch.object(orchestration_module, "_dispatch_command", side_effect=fake_dispatch),
        patch.object(orchestration_module, "_build_hook_registry", return_value=None),
    ):
        result = orchestration_module._execute_run_dir(inp, tmp_path, ctx, config)

    assert result.summary is not None
    assert result.summary.resource_counts == counts
    assert result.summary.duration_s >= 0


def test_dispatch_apply_outcome(tmp_path: Path) -> None:
    settings = TfDoSettings(work_dir=tmp_path)
    prepared = orchestration_module.PreparedRunDir(
        init_input=InitInput(settings=settings),
        lifecycle_flags=[],
    )
    inp = orchestration_module.RunOrchestrationInput(
        settings=settings,
        command=LifecycleCommand.APPLY,
        auto_approve=True,
    )
    counts = ResourceActionCounts(add=2, change=0, destroy=0, replace=0)
    apply_result = ApplyResult(exit_code=0, resource_counts=counts)

    with patch.object(orchestration_module.executor, executor_core.apply.__name__, return_value=apply_result):
        outcome = orchestration_module._dispatch_command(inp, prepared, [], "envs/dev/app")

    assert outcome.resource_counts == counts
    assert outcome.output_change_count is None


def test_dispatch_plan_outcome(tmp_path: Path) -> None:
    settings = TfDoSettings(work_dir=tmp_path)
    prepared = orchestration_module.PreparedRunDir(
        init_input=InitInput(settings=settings),
        lifecycle_flags=[],
    )
    inp = orchestration_module.RunOrchestrationInput(settings=settings, command=LifecycleCommand.PLAN)
    plan_result = PlanResult(
        exit_code=0,
        resource_counts=ResourceActionCounts(add=1, change=0, destroy=0, replace=0),
        has_applyable_changes=False,
    )

    with patch.object(orchestration_module.executor, executor_core.plan.__name__, return_value=plan_result):
        outcome = orchestration_module._dispatch_command(inp, prepared, [], "envs/dev/app")

    assert outcome.has_applyable_changes is False


def test_execute_run_dir_prep_failure_sets_fail_label(tmp_path: Path) -> None:
    settings = TfDoSettings(work_dir=tmp_path)
    config = _minimal_resolved_config()
    ctx = RunDirContext(name="app", path="envs/dev/app", repo_owner="o", repo_name="r")
    inp = orchestration_module.RunOrchestrationInput(settings=settings, command=LifecycleCommand.PLAN)

    with patch.object(orchestration_module, "prepare_run_dir", side_effect=RuntimeError("bad prep")):
        result = orchestration_module._execute_run_dir(inp, tmp_path, ctx, config)

    assert result.exit_code == 1
    assert result.summary is not None
    assert result.summary.failure_label == FAILURE_LABEL
