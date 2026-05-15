from __future__ import annotations

from pathlib import Path
from unittest.mock import call, patch

import pytest
import typer
from ask_shell._internal.interactive import confirm, select_list
from ask_shell.shell import run_and_wait

from tfdo._internal.config.config_file import CONFIG_FILENAME
from tfdo._internal.config.config_model import CiConfig, TfDoConfig
from tfdo._internal.sync.cmd_sync import _ensure_git_repo

_MODULE = _ensure_git_repo.__module__


def test_ensure_git_repo_skips_when_git_exists(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    config = TfDoConfig()
    with patch(f"{_MODULE}.{confirm.__name__}") as mock_confirm:
        _ensure_git_repo(tmp_path, config)
    mock_confirm.assert_not_called()


def test_ensure_git_repo_aborts_on_decline(tmp_path: Path) -> None:
    config = TfDoConfig()
    with (
        patch(f"{_MODULE}.{confirm.__name__}", return_value=False),
        pytest.raises(typer.Abort),
    ):
        _ensure_git_repo(tmp_path, config)


def test_ensure_git_repo_init_only(tmp_path: Path) -> None:
    config = TfDoConfig()
    confirm_responses = iter([True, False])
    with (
        patch(f"{_MODULE}.{confirm.__name__}", side_effect=confirm_responses),
        patch(f"{_MODULE}.{run_and_wait.__name__}") as mock_run,
    ):
        _ensure_git_repo(tmp_path, config)
    assert mock_run.call_args_list == _git_init_calls(tmp_path)


def _git_init_calls(work_dir: Path) -> list:
    return [
        call("git init", cwd=work_dir),
        call(f"git add {CONFIG_FILENAME}", cwd=work_dir),
        call("git commit -m 'Initial commit with tfdo.yaml'", cwd=work_dir),
    ]


def test_ensure_git_repo_init_and_create_gh_with_ci_config(tmp_path: Path) -> None:
    config = TfDoConfig(ci=CiConfig(repo_org="my-org", repo_name="my-repo"))
    confirm_responses = iter([True, True])
    with (
        patch(f"{_MODULE}.{confirm.__name__}", side_effect=confirm_responses),
        patch(f"{_MODULE}.{run_and_wait.__name__}") as mock_run,
        patch(f"{_MODULE}.{select_list.__name__}", return_value="private"),
    ):
        _ensure_git_repo(tmp_path, config)
    assert mock_run.call_args_list == [
        *_git_init_calls(tmp_path),
        call("gh repo create my-org/my-repo --source=. --push --private", cwd=tmp_path),
    ]


def test_ensure_git_repo_falls_back_to_dir_name(tmp_path: Path) -> None:
    config = TfDoConfig()
    confirm_responses = iter([True, True])
    with (
        patch(f"{_MODULE}.{confirm.__name__}", side_effect=confirm_responses),
        patch(f"{_MODULE}.{run_and_wait.__name__}") as mock_run,
        patch(f"{_MODULE}.{select_list.__name__}", return_value="public"),
    ):
        _ensure_git_repo(tmp_path, config)
    assert mock_run.call_args_list == [
        *_git_init_calls(tmp_path),
        call(f"gh repo create {tmp_path.name} --source=. --push --public", cwd=tmp_path),
    ]
