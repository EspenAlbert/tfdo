import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from ask_shell.shell import ShellRun
from typer.testing import CliRunner

from tfdo._internal.core import check_logic
from tfdo._internal.core.check_logic import (
    _build_fmt_command,
    _build_validate_command,
    _find_tf_directories,
    _parse_fmt_stdout,
    _parse_validate_json,
    check,
)
from tfdo._internal.models import CheckInput, InitMode
from tfdo._internal.settings import InteractiveMode, TfDoSettings

module_name = check.__module__
_patch_run = f"{module_name}.{check_logic.run_and_wait.__name__}"
_patch_init = f"{module_name}.{check_logic.init.__name__}"
runner = CliRunner()


def _make_settings(tmp_path: Path) -> TfDoSettings:
    return TfDoSettings.for_testing(tmp_path, work_dir=tmp_path, interactive=InteractiveMode.ALWAYS)


def _mock_run(exit_code: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    run = MagicMock(spec=ShellRun)
    run.exit_code = exit_code
    run.stdout = stdout
    run.stderr = stderr
    return run


VALID_JSON = json.dumps({"valid": True, "diagnostics": []})
INVALID_JSON = json.dumps(
    {
        "valid": False,
        "diagnostics": [
            {"severity": "error", "summary": "Missing required argument"},
            {"severity": "error", "summary": "Unsupported block type"},
        ],
    }
)


def _create_tf_tree(tmp_path: Path) -> list[Path]:
    """Creates root/ with main.tf, modules/vpc/ with vpc.tf, and .terraform/ (excluded)."""
    (tmp_path / "main.tf").touch()
    mod_dir = tmp_path / "modules" / "vpc"
    mod_dir.mkdir(parents=True)
    (mod_dir / "vpc.tf").touch()
    tf_internal = tmp_path / ".terraform" / "providers"
    tf_internal.mkdir(parents=True)
    (tf_internal / "something.tf").touch()
    return [tmp_path, mod_dir]


# --- pure function tests ---


def test_find_tf_directories(tmp_path: Path):
    expected = _create_tf_tree(tmp_path)
    result = _find_tf_directories(tmp_path)
    assert result == sorted(expected)


def test_build_fmt_command():
    assert _build_fmt_command("terraform", fix=False, diff=False) == "terraform fmt -check -recursive ."
    assert _build_fmt_command("terraform", fix=True, diff=False) == "terraform fmt -recursive ."
    assert _build_fmt_command("terraform", fix=False, diff=True) == "terraform fmt -check -diff -recursive ."


def test_parse_fmt_stdout():
    assert _parse_fmt_stdout("") == 0
    assert _parse_fmt_stdout("main.tf\nmodules/vpc/vpc.tf\n") == 2
    assert _parse_fmt_stdout("  \n") == 0


def test_build_validate_command():
    assert _build_validate_command("tofu") == "tofu validate -json"


def test_parse_validate_json():
    assert _parse_validate_json(VALID_JSON) == []
    errors = _parse_validate_json(INVALID_JSON)
    assert errors == ["Missing required argument", "Unsupported block type"]
    assert _parse_validate_json("") == []


# --- integration tests ---


def test_check_no_issues(tmp_path: Path):
    _create_tf_tree(tmp_path)
    for d in [tmp_path, tmp_path / "modules" / "vpc"]:
        (d / ".terraform").mkdir(exist_ok=True)
    settings = _make_settings(tmp_path)
    fmt_run = _mock_run(exit_code=0, stdout="")
    validate_runs = [_mock_run(stdout=VALID_JSON), _mock_run(stdout=VALID_JSON)]
    with patch(_patch_run, side_effect=[fmt_run, *validate_runs]):
        result = check(CheckInput(settings=settings))
    assert result.exit_code == 0
    assert result.fmt_issues == 0
    assert result.validation_errors == []
    assert result.directories_checked == 2


def test_check_fmt_issues(tmp_path: Path):
    (tmp_path / "main.tf").touch()
    (tmp_path / ".terraform").mkdir()
    settings = _make_settings(tmp_path)
    fmt_run = _mock_run(exit_code=3, stdout="main.tf\n")
    validate_run = _mock_run(stdout=VALID_JSON)
    with patch(_patch_run, side_effect=[fmt_run, validate_run]):
        result = check(CheckInput(settings=settings))
    assert result.exit_code == 1
    assert result.fmt_issues == 1


def test_check_fix_mode_ignores_fmt_issues(tmp_path: Path):
    (tmp_path / "main.tf").touch()
    (tmp_path / ".terraform").mkdir()
    settings = _make_settings(tmp_path)
    fmt_run = _mock_run(exit_code=0, stdout="main.tf\n")
    validate_run = _mock_run(stdout=VALID_JSON)
    with patch(_patch_run, side_effect=[fmt_run, validate_run]):
        result = check(CheckInput(settings=settings, fix=True))
    assert result.exit_code == 0
    assert result.fmt_issues == 0


def test_check_validation_errors(tmp_path: Path):
    (tmp_path / "main.tf").touch()
    (tmp_path / ".terraform").mkdir()
    settings = _make_settings(tmp_path)
    fmt_run = _mock_run(exit_code=0)
    validate_run = _mock_run(stdout=INVALID_JSON)
    with patch(_patch_run, side_effect=[fmt_run, validate_run]):
        result = check(CheckInput(settings=settings))
    assert result.exit_code == 1
    assert len(result.validation_errors) == 2


def test_check_skips_uninitialized_dir_never_mode(tmp_path: Path):
    (tmp_path / "main.tf").touch()
    settings = _make_settings(tmp_path)
    fmt_run = _mock_run(exit_code=0)
    with patch(_patch_run, return_value=fmt_run):
        result = check(CheckInput(settings=settings, init_mode=InitMode.NEVER))
    assert result.directories_skipped == 1
    assert result.directories_checked == 0


def test_check_auto_init_on_missing_terraform_dir(tmp_path: Path):
    (tmp_path / "main.tf").touch()
    settings = _make_settings(tmp_path)
    fmt_run = _mock_run(exit_code=0)
    validate_run = _mock_run(stdout=VALID_JSON)
    mock_init_result = MagicMock()
    mock_init_result.exit_code = 0
    with (
        patch(_patch_run, side_effect=[fmt_run, validate_run]),
        patch(_patch_init, return_value=mock_init_result) as mock_init,
    ):
        result = check(CheckInput(settings=settings, init_mode=InitMode.AUTO))
    assert result.directories_checked == 1
    mock_init.assert_called_once()


def test_check_cmd_via_cli(tmp_path: Path):
    from tfdo._internal.core import cmd_check  # noqa: F401
    from tfdo._internal.typer_app import app

    (tmp_path / "main.tf").touch()
    (tmp_path / ".terraform").mkdir()
    fmt_run = _mock_run(exit_code=0)
    validate_run = _mock_run(stdout=VALID_JSON)
    with patch(_patch_run, side_effect=[fmt_run, validate_run]):
        result = runner.invoke(app, ["--work-dir", str(tmp_path), "check"])
    assert result.exit_code == 0
