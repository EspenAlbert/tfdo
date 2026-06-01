from pathlib import Path
from unittest.mock import patch

import pytest

from tfdo._internal.config.config_model import DependencyRef
from tfdo._internal.config.config_resolution import ResolvedConfig
from tfdo._internal.config.enums import LifecycleCommand, TagsInject
from tfdo._internal.core import executor as executor_core
from tfdo._internal.core import terraform_init as terraform_init_core
from tfdo._internal.models import (
    ApplyInput,
    ApplyResult,
    InitInput,
    InitMode,
    InitResult,
    OutputInput,
    OutputResult,
    PlanInput,
    PlanResult,
)
from tfdo._internal.output.apply_live_mode import ApplyLiveMode
from tfdo._internal.run import orchestration as orchestration_module
from tfdo._internal.run.run_context import RunDirContext
from tfdo._internal.run.run_dir_summary import (
    FAILURE_LABEL,
    ResourceActionCounts,
    build_run_dir_summary,
    skipped_run_dir_summary,
)
from tfdo._internal.settings import CheckConfig, InteractiveMode, TfDoSettings

_ORCH_DIRS = ("envs/staging/networking", "envs/staging/compute", "envs/staging/database")


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
    captured: list[PlanInput] = []

    def fake_plan(plan_input: PlanInput) -> PlanResult:
        captured.append(plan_input)
        return plan_result

    with patch.object(orchestration_module.executor, executor_core.plan.__name__, side_effect=fake_plan):
        outcome = orchestration_module._dispatch_command(inp, prepared, [], "envs/dev/app")

    assert outcome.has_applyable_changes is False
    assert len(captured) == 1
    assert not captured[0].orchestration_active


def test_dispatch_plan_passes_orchestration_active(tmp_path: Path) -> None:
    settings = TfDoSettings(work_dir=tmp_path)
    prepared = orchestration_module.PreparedRunDir(
        init_input=InitInput(settings=settings),
        lifecycle_flags=[],
    )
    inp = orchestration_module.RunOrchestrationInput(
        settings=settings,
        command=LifecycleCommand.PLAN,
        orchestration_active=True,
    )
    captured: list[PlanInput] = []

    with patch.object(
        orchestration_module.executor,
        executor_core.plan.__name__,
        side_effect=lambda plan_input: captured.append(plan_input) or PlanResult(exit_code=0),
    ):
        orchestration_module._dispatch_command(inp, prepared, [], "envs/dev/app")

    assert captured[0].orchestration_active


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


def _orch_two_wave_plan() -> orchestration_module.ExecutionPlan:
    return orchestration_module.ExecutionPlan(
        waves=[
            orchestration_module.ExecutionWave(wave_index=0, run_dirs=list(_ORCH_DIRS[:2])),
            orchestration_module.ExecutionWave(wave_index=1, run_dirs=[_ORCH_DIRS[2]]),
        ]
    )


def _orch_contexts_configs(tmp_path: Path) -> tuple[dict[str, RunDirContext], dict[str, ResolvedConfig]]:
    contexts = {p: RunDirContext(name=p, path=p, repo_owner="o", repo_name="r") for p in _ORCH_DIRS}
    configs = {p: _minimal_resolved_config() for p in _ORCH_DIRS}
    return contexts, configs


def _orch_result(
    rel: str,
    command: LifecycleCommand,
    *,
    exit_code: int = 0,
    skipped: bool = False,
    resource_counts: ResourceActionCounts | None = None,
    output_change_count: int | None = None,
) -> orchestration_module.RunDirResult:
    summary = (
        skipped_run_dir_summary(rel, command, exit_code)
        if skipped
        else build_run_dir_summary(
            run_dir=rel,
            command=command,
            exit_code=exit_code,
            skipped=False,
            duration_s=1.0,
            resource_counts=resource_counts,
            output_change_count=output_change_count,
        )
    )
    return orchestration_module.RunDirResult(run_dir=rel, exit_code=exit_code, skipped=skipped, summary=summary)


def _run_orch_execute_plan(
    tmp_path: Path,
    command: LifecycleCommand,
    results_by_dir: dict[str, orchestration_module.RunDirResult],
    *,
    on_failure: orchestration_module.FailureMode = orchestration_module.FailureMode.STOP,
    auto_approve: bool = False,
) -> list[orchestration_module.RunDirResult]:
    settings = TfDoSettings.for_testing(tmp_path, interactive=InteractiveMode.NEVER)
    plan = _orch_two_wave_plan()
    inp = orchestration_module.RunOrchestrationInput(
        settings=settings,
        command=command,
        parallel=1,
        on_failure=on_failure,
        auto_approve=auto_approve,
    )
    contexts, configs = _orch_contexts_configs(tmp_path)
    display = orchestration_module._create_orchestration_display(inp, plan)
    assert display is not None

    def fake_execute(
        _inp: object, run_dir: Path, *_args: object, **_kwargs: object
    ) -> orchestration_module.RunDirResult:
        return results_by_dir[str(run_dir.relative_to(tmp_path))]

    module_name = orchestration_module.__name__
    with (
        patch(f"{module_name}.{orchestration_module._execute_run_dir.__name__}", side_effect=fake_execute),
        patch(f"{module_name}.{orchestration_module._collect_dependency_outputs.__name__}", return_value=None),
        patch(f"{module_name}.{orchestration_module._log_run_dir_output.__name__}"),
        patch("time.monotonic", return_value=1.0),
    ):
        results = orchestration_module._execute_plan(plan, inp, tmp_path, contexts, configs, display)
        display.on_run_complete()
    return results


def _caplog_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.message for r in caplog.records]


def _happy_results(command: LifecycleCommand) -> dict[str, orchestration_module.RunDirResult]:
    plan_counts = ResourceActionCounts(add=3, change=1)
    return {
        _ORCH_DIRS[0]: _orch_result(
            _ORCH_DIRS[0],
            command,
            resource_counts=plan_counts,
            output_change_count=2 if command == LifecycleCommand.PLAN else None,
        ),
        _ORCH_DIRS[1]: _orch_result(_ORCH_DIRS[1], command, resource_counts=ResourceActionCounts(add=1)),
        _ORCH_DIRS[2]: _orch_result(_ORCH_DIRS[2], command, resource_counts=None),
    }


@pytest.mark.parametrize("command", [LifecycleCommand.PLAN, LifecycleCommand.APPLY])
def test_execute_plan_orchestration_ci(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, command: LifecycleCommand
) -> None:
    auto_approve = command == LifecycleCommand.APPLY
    results = _run_orch_execute_plan(tmp_path, command, _happy_results(command), auto_approve=auto_approve)
    messages = _caplog_messages(caplog)
    prefix = f"{command}:"
    assert orchestration_module.OrchestrationResult(results=results).exit_code == 0
    assert any(m.startswith("orchestration: wave 1/2 started") for m in messages)
    assert any(m.startswith("orchestration: wave 2/2 started") for m in messages)
    assert any(m.startswith("orchestration: complete 3 dirs, 2 waves") for m in messages)
    assert sum(1 for m in messages if m.startswith(f"{prefix} ✅")) == 3
    if command == LifecycleCommand.PLAN:
        assert not any(m.startswith("Apply:") for m in messages)
        assert not any("📋 Plan:" in m for m in messages)
    else:
        assert any(m.startswith("Apply:") for m in messages)


def test_execute_plan_orchestration_exit_code(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    by_dir = _happy_results(LifecycleCommand.PLAN)
    by_dir[_ORCH_DIRS[1]] = _orch_result(_ORCH_DIRS[1], LifecycleCommand.PLAN, exit_code=1)
    results = _run_orch_execute_plan(tmp_path, LifecycleCommand.PLAN, by_dir)
    assert orchestration_module.OrchestrationResult(results=results).exit_code == 1
    assert any(m.startswith("plan: ❌") and _ORCH_DIRS[1] in m for m in _caplog_messages(caplog))


@pytest.mark.parametrize("command", [LifecycleCommand.PLAN, LifecycleCommand.APPLY])
def test_execute_plan_orchestration_on_failure_stop(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, command: LifecycleCommand
) -> None:
    by_dir = _happy_results(command)
    by_dir[_ORCH_DIRS[1]] = _orch_result(_ORCH_DIRS[1], command, exit_code=1)
    auto_approve = command == LifecycleCommand.APPLY
    results = _run_orch_execute_plan(
        tmp_path, command, by_dir, on_failure=orchestration_module.FailureMode.STOP, auto_approve=auto_approve
    )
    messages = _caplog_messages(caplog)
    assert any(m.startswith(f"{command}: 🚫") and _ORCH_DIRS[2] in m for m in messages)
    skipped = [r for r in results if r.run_dir == _ORCH_DIRS[2]]
    assert len(skipped) == 1
    assert skipped[0].skipped


def test_dispatch_apply_passes_run_dir_key_and_live_mode(tmp_path: Path) -> None:
    settings = TfDoSettings(work_dir=tmp_path)
    prepared = orchestration_module.PreparedRunDir(
        init_input=InitInput(settings=settings),
        lifecycle_flags=[],
    )
    captured: list[ApplyInput] = []

    def fake_apply(apply_input: ApplyInput) -> ApplyResult:
        captured.append(apply_input)
        return ApplyResult(exit_code=0)

    inp = orchestration_module.RunOrchestrationInput(
        settings=settings,
        command=LifecycleCommand.APPLY,
        auto_approve=True,
        orchestration_active=True,
        run_dir_key="envs/dev/app",
        apply_live_mode=ApplyLiveMode.COMPACT,
    )
    with patch.object(orchestration_module.executor, executor_core.apply.__name__, side_effect=fake_apply):
        orchestration_module._dispatch_command(inp, prepared, [], "envs/dev/app")

    assert captured[0].run_dir_key == "envs/dev/app"
    assert captured[0].apply_live_mode == ApplyLiveMode.COMPACT


def test_execute_run_dir_sets_run_dir_key(tmp_path: Path) -> None:
    settings = TfDoSettings(work_dir=tmp_path)
    config = _minimal_resolved_config()
    ctx = RunDirContext(name="app", path="envs/dev/app", repo_owner="o", repo_name="r")
    inp = orchestration_module.RunOrchestrationInput(
        settings=settings,
        command=LifecycleCommand.PLAN,
        orchestration_active=True,
    )
    prepared = orchestration_module.PreparedRunDir(
        init_input=InitInput(settings=settings),
        lifecycle_flags=[],
    )
    captured: list[orchestration_module.RunOrchestrationInput] = []

    def fake_dispatch(
        run_inp: orchestration_module.RunOrchestrationInput,
        *_args: object,
        **_kwargs: object,
    ) -> orchestration_module._DispatchOutcome:
        captured.append(run_inp)
        return orchestration_module._DispatchOutcome(0, False, "", "", None, None, None)

    with (
        patch.object(orchestration_module, "prepare_run_dir", return_value=prepared),
        patch.object(orchestration_module, "_dispatch_command", side_effect=fake_dispatch),
    ):
        orchestration_module._execute_run_dir(inp, tmp_path, ctx, config)

    assert captured[0].run_dir_key == "envs/dev/app"
