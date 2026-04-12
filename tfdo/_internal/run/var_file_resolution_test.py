from pathlib import Path

import pytest

from tfdo._internal.run.var_file_resolution import (
    resolve_var_files,
    validate_var_files,
    var_file_flags,
)


def test_resolve_var_files_config_and_cli(tmp_path: Path):
    result = resolve_var_files(tmp_path, ["a.tfvars"], ["b.tfvars.json"])
    assert result == [(tmp_path / "a.tfvars").resolve(), (tmp_path / "b.tfvars.json").resolve()]


def test_resolve_var_files_empty(tmp_path: Path):
    assert resolve_var_files(tmp_path, [], []) == []


def test_validate_var_files_existing(tmp_path: Path):
    f = tmp_path / "ok.tfvars"
    f.write_text("")
    validate_var_files([f])


def test_validate_var_files_missing_raises(tmp_path: Path):
    missing1 = tmp_path / "gone.tfvars"
    missing2 = tmp_path / "also_gone.tfvars"
    with pytest.raises(FileNotFoundError, match="gone.tfvars"):
        validate_var_files([missing1, missing2])
    with pytest.raises(FileNotFoundError, match="also_gone.tfvars"):
        validate_var_files([missing1, missing2])


def test_var_file_flags(tmp_path: Path):
    paths = [tmp_path / "a.tfvars", tmp_path / "b.tfvars.json"]
    flags = var_file_flags(paths)
    assert flags == [f"-var-file={paths[0]}", f"-var-file={paths[1]}"]
