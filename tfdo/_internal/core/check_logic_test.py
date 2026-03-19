from pathlib import Path
from unittest.mock import MagicMock, patch

from ask_shell.shell import ShellRun
from typer.testing import CliRunner

from tfdo._internal.core import check_logic
from tfdo._internal.core.check_logic import (
    _build_fmt_command,
    _build_validate_command,
    _parse_fmt_files,
    check,
)
from tfdo._internal.core.tf_files import find_tf_directories
from tfdo._internal.models import CheckInput, DirCheckResult, InitMode, ValidateDiagnostic, ValidateOutput
from tfdo._internal.settings import InteractiveMode, TfDoSettings

module_name = check.__module__
_patch_run = f"{module_name}.{check_logic.run_and_wait.__name__}"
_patch_init = f"{module_name}.{check_logic.init.__name__}"
runner = CliRunner()

VALID_OUTPUT = ValidateOutput()
INVALID_OUTPUT = ValidateOutput(
    valid=False,
    diagnostics=[
        ValidateDiagnostic(severity="error", summary="Missing required argument"),
        ValidateDiagnostic(severity="error", summary="Unsupported block type"),
    ],
)


def _make_settings(tmp_path: Path) -> TfDoSettings:
    return TfDoSettings.for_testing(tmp_path, work_dir=tmp_path, interactive=InteractiveMode.ALWAYS)


def _mock_run(
    exit_code: int = 0, stdout: str = "", stderr: str = "", validate_output: ValidateOutput | None = None
) -> MagicMock:
    run = MagicMock(spec=ShellRun)
    run.exit_code = exit_code
    run.stdout = stdout
    run.stdout_one_line = "".join(stdout.splitlines()).strip()
    run.stderr = stderr
    run.parse_output.return_value = validate_output or ValidateOutput()
    return run


def _create_tf_tree(tmp_path: Path) -> list[Path]:
    (tmp_path / "main.tf").touch()
    mod_dir = tmp_path / "modules" / "vpc"
    mod_dir.mkdir(parents=True)
    (mod_dir / "vpc.tf").touch()
    tf_internal = tmp_path / ".terraform" / "providers"
    tf_internal.mkdir(parents=True)
    (tf_internal / "something.tf").touch()
    return [tmp_path, mod_dir]


def _create_tf_tree_with_examples(tmp_path: Path) -> list[Path]:
    _create_tf_tree(tmp_path)
    examples_dir = tmp_path / "examples" / "demo"
    examples_dir.mkdir(parents=True)
    (examples_dir / "main.tf").touch()
    return [examples_dir, tmp_path / "modules" / "vpc", tmp_path]


# --- pure function tests ---


def test_find_tf_directories(tmp_path: Path):
    expected = _create_tf_tree(tmp_path)
    result = find_tf_directories(tmp_path)
    assert result == sorted(expected)


def test_find_tf_directories_with_exclude(tmp_path: Path):
    _create_tf_tree_with_examples(tmp_path)
    result = find_tf_directories(tmp_path, exclude_patterns=["examples/*"])
    assert tmp_path / "examples" / "demo" not in result
    assert tmp_path / "modules" / "vpc" in result
    assert tmp_path in result


def test_find_tf_directories_with_include(tmp_path: Path):
    _create_tf_tree_with_examples(tmp_path)
    result = find_tf_directories(tmp_path, include_patterns=["modules/*"])
    assert result == [tmp_path / "modules" / "vpc"]


def test_find_tf_directories_include_and_exclude(tmp_path: Path):
    _create_tf_tree_with_examples(tmp_path)
    legacy = tmp_path / "modules" / "legacy-net"
    legacy.mkdir(parents=True)
    (legacy / "main.tf").touch()
    result = find_tf_directories(tmp_path, include_patterns=["modules/*"], exclude_patterns=["modules/legacy*"])
    assert result == [tmp_path / "modules" / "vpc"]


def test_build_fmt_command():
    assert _build_fmt_command("terraform", fix=False, diff=False) == "terraform fmt -check ."
    assert _build_fmt_command("terraform", fix=True, diff=False) == "terraform fmt ."
    assert _build_fmt_command("terraform", fix=False, diff=True) == "terraform fmt -check -diff ."


def test_parse_fmt_files():
    assert _parse_fmt_files("") == []
    assert _parse_fmt_files("main.tf\nmodules/vpc/vpc.tf\n") == ["main.tf", "modules/vpc/vpc.tf"]
    assert _parse_fmt_files("  \n") == []


def test_build_validate_command():
    assert _build_validate_command("tofu") == "tofu validate -json"


def test_validate_output_model():
    assert VALID_OUTPUT.error_summaries == []
    assert INVALID_OUTPUT.error_summaries == ["Missing required argument", "Unsupported block type"]
    assert ValidateOutput().error_summaries == []


# --- integration tests ---


def test_check_no_issues(tmp_path: Path):
    _create_tf_tree(tmp_path)
    for d in [tmp_path, tmp_path / "modules" / "vpc"]:
        (d / ".terraform").mkdir(exist_ok=True)
    settings = _make_settings(tmp_path)
    mock_run = _mock_run(exit_code=0, stdout="", validate_output=VALID_OUTPUT)
    with patch(_patch_run, return_value=mock_run):
        result = check(CheckInput(settings=settings))
    assert result.exit_code == 0
    assert result.total_fmt_files == []
    assert result.total_validation_errors == []
    assert result.directories_checked == 2
    assert len(result.dir_results) == 2


def test_check_fmt_issues(tmp_path: Path):
    (tmp_path / "main.tf").touch()
    (tmp_path / ".terraform").mkdir()
    settings = _make_settings(tmp_path)
    fmt_run = _mock_run(exit_code=3, stdout="main.tf\n")
    validate_run = _mock_run(validate_output=VALID_OUTPUT)
    with patch(_patch_run, side_effect=[fmt_run, validate_run]):
        result = check(CheckInput(settings=settings))
    assert result.exit_code == 1
    assert result.total_fmt_files == ["main.tf"]


def test_check_fix_mode_ignores_fmt_issues(tmp_path: Path):
    (tmp_path / "main.tf").touch()
    (tmp_path / ".terraform").mkdir()
    settings = _make_settings(tmp_path)
    fmt_run = _mock_run(exit_code=0, stdout="main.tf\n")
    validate_run = _mock_run(validate_output=VALID_OUTPUT)
    with patch(_patch_run, side_effect=[fmt_run, validate_run]):
        result = check(CheckInput(settings=settings, fix=True))
    assert result.exit_code == 0
    assert result.total_fmt_files == []


def test_check_validation_errors(tmp_path: Path):
    (tmp_path / "main.tf").touch()
    (tmp_path / ".terraform").mkdir()
    settings = _make_settings(tmp_path)
    fmt_run = _mock_run(exit_code=0)
    validate_run = _mock_run(validate_output=INVALID_OUTPUT)
    with patch(_patch_run, side_effect=[fmt_run, validate_run]):
        result = check(CheckInput(settings=settings))
    assert result.exit_code == 1
    assert len(result.total_validation_errors) == 2


def test_check_skips_uninitialized_dir_never_mode(tmp_path: Path):
    (tmp_path / "main.tf").touch()
    settings = _make_settings(tmp_path)
    fmt_run = _mock_run(exit_code=0)
    with patch(_patch_run, return_value=fmt_run):
        result = check(CheckInput(settings=settings, init_mode=InitMode.NEVER))
    assert result.directories_skipped == [tmp_path]
    assert result.directories_checked == 0


def test_check_auto_init_on_missing_terraform_dir(tmp_path: Path):
    (tmp_path / "main.tf").touch()
    settings = _make_settings(tmp_path)
    fmt_run = _mock_run(exit_code=0)
    validate_run = _mock_run(validate_output=VALID_OUTPUT)
    mock_init_result = MagicMock()
    mock_init_result.exit_code = 0
    with (
        patch(_patch_run, side_effect=[fmt_run, validate_run]),
        patch(_patch_init, return_value=mock_init_result) as mock_init,
    ):
        result = check(CheckInput(settings=settings, init_mode=InitMode.AUTO))
    assert result.directories_checked == 1
    mock_init.assert_called_once()


def test_check_with_exclude(tmp_path: Path):
    _create_tf_tree_with_examples(tmp_path)
    for d in [tmp_path, tmp_path / "modules" / "vpc"]:
        (d / ".terraform").mkdir(exist_ok=True)
    settings = _make_settings(tmp_path)
    mock_run = _mock_run(exit_code=0, validate_output=VALID_OUTPUT)
    with patch(_patch_run, return_value=mock_run):
        result = check(CheckInput(settings=settings, exclude_patterns=["examples/*"]))
    assert result.directories_checked == 2


def test_check_dir_results_have_correct_issues(tmp_path: Path):
    (tmp_path / "main.tf").touch()
    (tmp_path / ".terraform").mkdir()
    settings = _make_settings(tmp_path)
    fmt_run = _mock_run(exit_code=3, stdout="main.tf\n")
    validate_run = _mock_run(validate_output=INVALID_OUTPUT)
    with patch(_patch_run, side_effect=[fmt_run, validate_run]):
        result = check(CheckInput(settings=settings))
    assert len(result.dir_results) == 1
    dr = result.dir_results[0]
    assert dr.directory == tmp_path
    assert dr.fmt_files == ["main.tf"]
    assert len(dr.validation_errors) == 2
    assert dr.has_issues


def test_dir_check_result_properties():
    ok = DirCheckResult(directory=Path("/a"))
    assert not ok.has_issues
    fmt_bad = DirCheckResult(directory=Path("/b"), fmt_files=["x.tf", "y.tf"])
    assert fmt_bad.has_issues
    val_bad = DirCheckResult(directory=Path("/c"), validation_errors=["err"])
    assert val_bad.has_issues


def test_check_cmd_via_cli(tmp_path: Path):
    from tfdo._internal.core import cmd_check  # noqa: F401
    from tfdo._internal.typer_app import app

    (tmp_path / "main.tf").touch()
    (tmp_path / ".terraform").mkdir()
    mock_run = _mock_run(exit_code=0, validate_output=VALID_OUTPUT)
    with patch(_patch_run, return_value=mock_run):
        result = runner.invoke(app, ["--work-dir", str(tmp_path), "check"])
    assert result.exit_code == 0


def test_check_cmd_with_exclude_via_cli(tmp_path: Path):
    from tfdo._internal.core import cmd_check  # noqa: F401
    from tfdo._internal.typer_app import app

    _create_tf_tree_with_examples(tmp_path)
    for d in [tmp_path, tmp_path / "modules" / "vpc"]:
        (d / ".terraform").mkdir(exist_ok=True)
    mock_run = _mock_run(exit_code=0, validate_output=VALID_OUTPUT)
    with patch(_patch_run, return_value=mock_run):
        result = runner.invoke(app, ["--work-dir", str(tmp_path), "check", "--exclude", "examples/*"])
    assert result.exit_code == 0
