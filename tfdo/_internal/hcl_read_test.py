from __future__ import annotations

from pathlib import Path

from tfdo._internal.hcl_read import LOCK_FILENAME, find_lock_file


def _git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    return repo


def test_find_lock_file_returns_nearest_lock(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)
    (repo / LOCK_FILENAME).write_text('provider "registry.terraform.io/hashicorp/aws" { version = "1.0.0" }\n')
    run_dir = repo / "envs" / "prod" / "app"
    run_dir.mkdir(parents=True)
    assert find_lock_file(run_dir) == repo / LOCK_FILENAME


def test_find_lock_file_prefers_run_dir_lock(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)
    (repo / LOCK_FILENAME).write_text('provider "registry.terraform.io/hashicorp/aws" { version = "1.0.0" }\n')
    run_dir = repo / "envs" / "prod" / "app"
    run_dir.mkdir(parents=True)
    run_lock = run_dir / LOCK_FILENAME
    run_lock.write_text('provider "registry.terraform.io/hashicorp/aws" { version = "2.0.0" }\n')
    assert find_lock_file(run_dir) == run_lock


def test_find_lock_file_returns_none_when_missing(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)
    run_dir = repo / "envs" / "prod" / "app"
    run_dir.mkdir(parents=True)
    assert find_lock_file(run_dir) is None


def test_find_lock_file_outside_git_checks_work_dir_only(tmp_path: Path) -> None:
    work_dir = tmp_path / "standalone"
    work_dir.mkdir()
    assert find_lock_file(work_dir) is None
    lock = work_dir / LOCK_FILENAME
    lock.write_text('provider "registry.terraform.io/hashicorp/aws" { version = "1.0.0" }\n')
    assert find_lock_file(work_dir) == lock
