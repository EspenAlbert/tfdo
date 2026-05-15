from pathlib import Path
from unittest.mock import patch

from tfdo._internal.config.config_model import DependencyRef
from tfdo._internal.config.config_resolution import ResolvedConfig
from tfdo._internal.config.enums import TagsInject
from tfdo._internal.models import OutputInput, OutputResult
from tfdo._internal.run import orchestration as orchestration_module
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

    with patch.object(orchestration_module.executor, "output_json", side_effect=fake_output):
        out = orchestration_module._collect_dependency_outputs(settings, run_dir, config)

    assert out == {"id": "out"}
    assert len(captured) == 1
    assert captured[0].settings.work_dir == run_dir
    assert captured[0].settings.tf_version == "1.12.1"
    assert captured[0].settings.binary == "terraform"


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
