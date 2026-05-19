from __future__ import annotations

import subprocess
from pathlib import Path

from tfdo._internal.config.config_file import resolve_run_context_label, root_tfdo_config
from tfdo._internal.models import PlanInput
from tfdo._internal.settings import TfDoSettings


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)


def test_resolve_run_context_label_from_discovery_pattern(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "tfdo.yaml").write_text("run_dir_discovery: '{env}/{run_dir}'\n")
    run_dir = tmp_path / "00_debug" / "32_cluster_module_online"
    run_dir.mkdir(parents=True)
    config = root_tfdo_config(tmp_path)
    assert config is not None
    assert config.parsed_pattern().match("00_debug/32_cluster_module_online") == {
        "env": "00_debug",
        "run_dir": "32_cluster_module_online",
    }
    assert resolve_run_context_label(run_dir) == "00_debug/32_cluster_module_online"


def test_resolve_run_context_label_includes_optional_team(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "tfdo.yaml").write_text("run_dir_discovery: 'envs/{env}/{team}?/{run_dir}'\n")
    run_dir = tmp_path / "envs" / "00_debug" / "platform" / "module_online"
    run_dir.mkdir(parents=True)
    assert resolve_run_context_label(run_dir) == "00_debug/platform/module_online"
    no_team = tmp_path / "envs" / "00_debug" / "module_online"
    no_team.mkdir(parents=True)
    assert resolve_run_context_label(no_team) == "00_debug/module_online"


def test_run_context_label_falls_back_to_last_two_path_segments(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "tfdo.yaml").write_text("run_dir_discovery: '{env}/{run_dir}'\n")
    run_dir = tmp_path / "code" / "00_debug" / "32_cluster_module_online"
    run_dir.mkdir(parents=True)
    assert resolve_run_context_label(run_dir) == "00_debug/32_cluster_module_online"


def test_plan_input_sets_run_context_label(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "tfdo.yaml").write_text("run_dir_discovery: '{env}/{run_dir}'\n")
    run_dir = tmp_path / "00_debug" / "32_cluster_module_online"
    run_dir.mkdir(parents=True)
    plan_input = PlanInput(settings=TfDoSettings(work_dir=run_dir))
    assert plan_input.run_context_label == "00_debug/32_cluster_module_online"
