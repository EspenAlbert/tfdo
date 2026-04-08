from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from tfdo._internal.config.config_model import DependencyRef
from tfdo._internal.config.config_resolution import ResolvedConfig
from tfdo._internal.config.enums import TagsInject
from tfdo._internal.core import executor
from tfdo._internal.models import InitResult, PlanResult
from tfdo._internal.run.discovery import DiscoveredRunDir
from tfdo._internal.run.orchestration import (
    DependencyGraph,
    FailureMode,
    LifecycleCommand,
    OrchestrationResult,
    RunDirResult,
    RunOrchestrationInput,
    _resolve_ref,
    build_dependency_graph,
    prepare_run_dir,
    run_orchestration,
)
from tfdo._internal.run.run_context import RunDirContext
from tfdo._internal.settings import CheckConfig, TfDoSettings

TF_BACKEND = 'terraform {\n  backend "s3" {\n    bucket = "test"\n  }\n}\n'


def _resolved_config(**overrides) -> ResolvedConfig:  # pyright: ignore[reportReturnType]
    defaults: dict = dict(
        binary="terraform",
        tf_version=None,
        backend=None,
        tags={},
        var_files=[],
        tags_inject=TagsInject.NEVER,
        hook_configs=[],
        dependencies=[],
        check=CheckConfig(),
    )
    defaults.update(overrides)
    return ResolvedConfig(**defaults)  # pyright: ignore[reportCallIssue]


def test_dependency_graph_no_deps():
    graph = DependencyGraph(edges={"a": set(), "b": set(), "c": set()})
    plan = graph.to_waves()
    assert len(plan.waves) == 1
    assert sorted(plan.waves[0].run_dirs) == ["a", "b", "c"]


def test_dependency_graph_with_deps():
    graph = DependencyGraph(edges={"a": set(), "b": {"a"}, "c": {"b"}})
    plan = graph.to_waves()
    assert len(plan.waves) == 3
    assert plan.waves[0].run_dirs == ["a"]
    assert plan.waves[1].run_dirs == ["b"]
    assert plan.waves[2].run_dirs == ["c"]


def test_dependency_graph_cycle_detected():
    graph = DependencyGraph(edges={"a": {"b"}, "b": {"a"}})
    with pytest.raises(ValueError, match="cycle"):
        graph.to_waves()


def test_resolve_ref_sibling():
    all_paths = {"envs/dev/network", "envs/dev/compute"}
    assert _resolve_ref("network", "envs/dev/compute", all_paths) == "envs/dev/network"


def test_resolve_ref_missing_raises():
    with pytest.raises(ValueError, match="not a discovered run_dir"):
        _resolve_ref("missing", "envs/dev/compute", {"envs/dev/compute"})


def test_build_dependency_graph_from_configs():
    discovered = [
        DiscoveredRunDir(path=Path("/r/envs/dev/net"), relative_path="envs/dev/net", selectors={}),
        DiscoveredRunDir(path=Path("/r/envs/dev/app"), relative_path="envs/dev/app", selectors={}),
    ]
    configs = {
        "envs/dev/net": _resolved_config(),
        "envs/dev/app": _resolved_config(dependencies=[DependencyRef(ref="net")]),
    }
    graph = build_dependency_graph(discovered, configs)
    assert graph.edges["envs/dev/app"] == {"envs/dev/net"}
    assert graph.edges["envs/dev/net"] == set()


def test_prepare_run_dir_builds_init_input(tmp_path: Path):
    run_dir = tmp_path / "envs" / "dev" / "api"
    run_dir.mkdir(parents=True)
    settings = TfDoSettings(work_dir=tmp_path)
    ctx = RunDirContext(name="api", path="envs/dev/api", repo_owner="o", repo_name="r")
    config = _resolved_config()
    prepared = prepare_run_dir(settings, run_dir, ctx, config, None)
    assert prepared.init_input.settings.work_dir == run_dir
    assert prepared.lifecycle_flags == []


def test_orchestration_result_exit_code():
    ok = OrchestrationResult(results=[RunDirResult(run_dir="a", exit_code=0)])
    assert ok.exit_code == 0
    failed = OrchestrationResult(
        results=[
            RunDirResult(run_dir="a", exit_code=0),
            RunDirResult(run_dir="b", exit_code=2),
        ]
    )
    assert failed.exit_code == 2


def _setup_repo(tmp_path: Path, run_dirs: list[str], discovery_pattern: str, configs: dict[str, dict] | None = None):
    (tmp_path / ".git").mkdir()
    root_config = {"run_dir_discovery": discovery_pattern}
    (tmp_path / "tfdo.yaml").write_text(yaml.dump(root_config))
    for rd in run_dirs:
        d = tmp_path / rd
        d.mkdir(parents=True, exist_ok=True)
        (d / "main.tf").write_text(TF_BACKEND)
        if configs and rd in configs:
            (d / "tfdo.yaml").write_text(yaml.dump(configs[rd]))


def test_run_orchestration_dry_run(tmp_path: Path):
    _setup_repo(tmp_path, ["envs/dev/api", "envs/dev/web"], "envs/{env}/{app}")
    settings = TfDoSettings(work_dir=tmp_path)
    inp = RunOrchestrationInput(settings=settings, command=LifecycleCommand.PLAN, dry_run=True)
    result = run_orchestration(inp)
    assert len(result.results) == 2
    assert all(r.skipped for r in result.results)
    assert result.exit_code == 0


def test_run_orchestration_with_mocked_executor(tmp_path: Path):
    _setup_repo(
        tmp_path,
        ["envs/dev/network", "envs/dev/compute"],
        "envs/{env}/{app}",
        configs={"envs/dev/compute": {"dependencies": [{"ref": "network"}]}},
    )
    settings = TfDoSettings(work_dir=tmp_path)
    inp = RunOrchestrationInput(settings=settings, command=LifecycleCommand.PLAN, auto_approve=True, parallel=2)

    executor_module = executor.__name__
    with (
        patch(f"{executor_module}.{executor.init.__name__}", return_value=InitResult(exit_code=0, attempts_used=1)),
        patch(f"{executor_module}.{executor.plan.__name__}", return_value=PlanResult(exit_code=0)),
    ):
        result = run_orchestration(inp)

    assert result.exit_code == 0
    assert len(result.results) == 2
    dirs = [r.run_dir for r in result.results]
    assert dirs.index("envs/dev/network") < dirs.index("envs/dev/compute")


def test_run_orchestration_continue_on_error(tmp_path: Path):
    _setup_repo(tmp_path, ["envs/dev/a", "envs/dev/b"], "envs/{env}/{app}")
    settings = TfDoSettings(work_dir=tmp_path)

    call_count = 0

    def mock_init(input_model):
        nonlocal call_count
        call_count += 1
        return InitResult(exit_code=1, attempts_used=1, stderr="init failed")

    inp = RunOrchestrationInput(
        settings=settings, command=LifecycleCommand.PLAN, on_failure=FailureMode.CONTINUE, parallel=2
    )
    executor_module = executor.__name__
    with patch(f"{executor_module}.{executor.init.__name__}", side_effect=mock_init):
        result = run_orchestration(inp)

    assert result.exit_code != 0
    assert call_count == 2


def test_run_orchestration_stops_on_first_failure(tmp_path: Path):
    _setup_repo(
        tmp_path,
        ["envs/dev/network", "envs/dev/compute"],
        "envs/{env}/{app}",
        configs={"envs/dev/compute": {"dependencies": [{"ref": "network"}]}},
    )
    settings = TfDoSettings(work_dir=tmp_path)
    inp = RunOrchestrationInput(settings=settings, command=LifecycleCommand.PLAN, parallel=2)

    executor_module = executor.__name__
    with patch(
        f"{executor_module}.{executor.init.__name__}",
        return_value=InitResult(exit_code=1, attempts_used=1, stderr="init failed"),
    ):
        result = run_orchestration(inp)

    assert result.exit_code != 0
    compute_result = next(r for r in result.results if r.run_dir == "envs/dev/compute")
    assert compute_result.skipped


def test_run_orchestration_selector_filter(tmp_path: Path):
    _setup_repo(tmp_path, ["envs/dev/api", "envs/staging/api"], "envs/{env}/{app}")
    settings = TfDoSettings(work_dir=tmp_path)
    inp = RunOrchestrationInput(
        settings=settings,
        command=LifecycleCommand.PLAN,
        dry_run=True,
        selector_filters={"env": "dev"},
    )
    result = run_orchestration(inp)
    assert len(result.results) == 1
    assert result.results[0].run_dir == "envs/dev/api"
