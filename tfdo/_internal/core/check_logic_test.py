from pathlib import Path
from unittest.mock import MagicMock, patch

from ask_shell.shell import ShellRun
from typer.testing import CliRunner

from tfdo._internal import settings as settings_mod
from tfdo._internal.core import check_logic
from tfdo._internal.core.check_logic import (
    _build_fmt_command,
    _build_validate_command,
    _parse_fmt_files,
    _run_tflint,
    check,
)
from tfdo._internal.core.tf_files import find_tf_directories
from tfdo._internal.models import (
    CheckInput,
    DirCheckResult,
    InitMode,
    TflintIssue,
    TflintOutput,
    TflintRange,
    TflintRule,
    ValidateDiagnostic,
    ValidateOutput,
)
from tfdo._internal.settings import (
    CheckConfig,
    InteractiveMode,
    TfDoSettings,
    TfDoUserConfig,
    load_user_config,
    resolve_tflint_flag,
)

module_name = check.__module__
_patch_run = f"{module_name}.{check_logic.run_and_wait.__name__}"
_patch_init = f"{module_name}.{check_logic.init.__name__}"
_patch_tflint_available = f"{module_name}.{check_logic._tflint_available.__name__}"
_patch_user_config_dir = f"{settings_mod.__name__}.{settings_mod.platformdirs.__name__}.user_config_dir"
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
    exit_code: int = 0,
    stdout: str = "",
    stderr: str = "",
    validate_output: ValidateOutput | None = None,
    tflint_output: TflintOutput | None = None,
) -> MagicMock:
    run = MagicMock(spec=ShellRun)
    run.exit_code = exit_code
    run.stdout = stdout
    run.stdout_one_line = "".join(stdout.splitlines()).strip()
    run.stderr = stderr
    outputs: dict[type, object] = {ValidateOutput: validate_output or ValidateOutput()}
    if tflint_output is not None:
        outputs[TflintOutput] = tflint_output
    run.parse_output.side_effect = lambda output_t, **_kwargs: outputs.get(output_t, output_t())
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


def test_check_init_failure_skips_directory(tmp_path: Path):
    (tmp_path / "main.tf").touch()
    settings = _make_settings(tmp_path)
    fmt_run = _mock_run(exit_code=0)
    mock_init_result = MagicMock()
    mock_init_result.exit_code = 1
    with (
        patch(_patch_run, return_value=fmt_run),
        patch(_patch_init, return_value=mock_init_result),
    ):
        result = check(CheckInput(settings=settings, init_mode=InitMode.AUTO))
    assert result.directories_skipped == [tmp_path]
    assert result.directories_checked == 0
    assert result.exit_code == 0


def test_check_empty_repo(tmp_path: Path):
    settings = _make_settings(tmp_path)
    result = check(CheckInput(settings=settings))
    assert result.exit_code == 0
    assert result.dir_results == []
    assert result.directories_checked == 0


def test_validate_output_ignores_warnings():
    output = ValidateOutput(
        valid=False,
        diagnostics=[
            ValidateDiagnostic(severity="warning", summary="Deprecated attribute"),
            ValidateDiagnostic(severity="error", summary="Missing required argument"),
        ],
    )
    assert output.error_summaries == ["Missing required argument"]


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


# --- tflint tests ---

TFLINT_CLEAN_OUTPUT = TflintOutput()

TFLINT_ISSUES_OUTPUT = TflintOutput(
    issues=[
        TflintIssue(
            rule=TflintRule(
                name="terraform_unused_declarations",
                severity="warning",
                link="https://github.com/terraform-linters/tflint-ruleset-terraform/blob/main/docs/rules/terraform_unused_declarations.md",
            ),
            message='variable "unused" is declared but not used',
            range=TflintRange(filename="variables.tf"),
        ),
        TflintIssue(
            rule=TflintRule(name="terraform_naming_convention", severity="notice"),
            message="variable name 'BadName' must match snake_case",
            range=TflintRange(filename="variables.tf"),
        ),
    ],
)


def test_tflint_output_parsing():
    assert TFLINT_CLEAN_OUTPUT.issues == []
    assert TFLINT_CLEAN_OUTPUT.errors == []


def test_tflint_output_parsing_with_issues():
    output = TFLINT_ISSUES_OUTPUT
    assert len(output.issues) == 2
    assert output.issues[0].rule.name == "terraform_unused_declarations"
    assert output.issues[0].rule.severity == "warning"
    assert output.issues[0].range.filename == "variables.tf"
    assert output.issues[1].message == "variable name 'BadName' must match snake_case"


def test_tflint_issue_display():
    issue = TflintIssue(
        rule=TflintRule(name="terraform_unused_declarations", severity="warning"),
        message='variable "foo" is declared but not used',
        range=TflintRange(filename="variables.tf"),
    )
    assert "[warning]" in issue.display
    assert "terraform_unused_declarations" in issue.display
    assert "variables.tf" in issue.display


def test_run_tflint_clean(tmp_path: Path):
    mock_run = _mock_run(exit_code=0, tflint_output=TFLINT_CLEAN_OUTPUT)
    with patch(_patch_run, return_value=mock_run):
        issues = _run_tflint(tmp_path)
    assert issues == []


def test_run_tflint_with_issues(tmp_path: Path):
    mock_run = _mock_run(exit_code=2, tflint_output=TFLINT_ISSUES_OUTPUT)
    with patch(_patch_run, return_value=mock_run):
        issues = _run_tflint(tmp_path)
    assert len(issues) == 2


def test_run_tflint_parse_failure(tmp_path: Path):
    mock_run = MagicMock(spec=ShellRun)
    mock_run.parse_output.side_effect = ValueError("bad data")
    with patch(_patch_run, return_value=mock_run):
        issues = _run_tflint(tmp_path)
    assert issues == []


def test_check_with_tflint(tmp_path: Path):
    (tmp_path / "main.tf").touch()
    (tmp_path / ".terraform").mkdir()
    settings = _make_settings(tmp_path)
    fmt_run = _mock_run(exit_code=0)
    validate_run = _mock_run(validate_output=VALID_OUTPUT)
    tflint_run = _mock_run(exit_code=2, tflint_output=TFLINT_ISSUES_OUTPUT)
    with (
        patch(_patch_run, side_effect=[fmt_run, validate_run, tflint_run]),
        patch(_patch_tflint_available, return_value=True),
    ):
        result = check(CheckInput(settings=settings, tflint=True))
    assert result.exit_code == 1
    assert len(result.total_tflint_issues) == 2
    assert result.dir_results[0].has_issues


def test_check_tflint_false_skips(tmp_path: Path):
    (tmp_path / "main.tf").touch()
    (tmp_path / ".terraform").mkdir()
    settings = _make_settings(tmp_path)
    mock_run = _mock_run(exit_code=0, validate_output=VALID_OUTPUT)
    with patch(_patch_run, return_value=mock_run):
        result = check(CheckInput(settings=settings, tflint=False))
    assert result.exit_code == 0
    assert result.total_tflint_issues == []


def test_check_tflint_not_on_path(tmp_path: Path):
    (tmp_path / "main.tf").touch()
    (tmp_path / ".terraform").mkdir()
    settings = _make_settings(tmp_path)
    mock_run = _mock_run(exit_code=0, validate_output=VALID_OUTPUT)
    with (
        patch(_patch_run, return_value=mock_run),
        patch(_patch_tflint_available, return_value=False),
    ):
        result = check(CheckInput(settings=settings, tflint=True))
    assert result.exit_code == 0
    assert result.total_tflint_issues == []


def test_dir_check_result_tflint_has_issues():
    issue = TflintIssue(rule=TflintRule(name="test_rule", severity="warning"), message="test")
    dr = DirCheckResult(directory=Path("/a"), tflint_issues=[issue])
    assert dr.has_issues


# --- user config / resolve_tflint_flag tests ---


def test_resolve_tflint_flag_cli_overrides(tmp_path: Path):
    settings = _make_settings(tmp_path)
    assert resolve_tflint_flag(True, settings)
    assert not resolve_tflint_flag(False, settings)


def test_resolve_tflint_flag_user_config(tmp_path: Path):
    settings = _make_settings(tmp_path)
    with patch(_patch_user_config_dir, return_value=str(tmp_path / "config")):
        config_path = settings.user_config_path
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("check:\n  tflint: true\n")
        assert resolve_tflint_flag(None, settings)


def test_resolve_tflint_flag_default(tmp_path: Path):
    settings = _make_settings(tmp_path)
    with patch(_patch_user_config_dir, return_value=str(tmp_path / "config")):
        assert not resolve_tflint_flag(None, settings)


def test_load_user_config_missing_file(tmp_path: Path):
    settings = _make_settings(tmp_path)
    with patch(_patch_user_config_dir, return_value=str(tmp_path / "config")):
        config = load_user_config(settings)
    assert config.check is None


def test_load_user_config_valid(tmp_path: Path):
    settings = _make_settings(tmp_path)
    with patch(_patch_user_config_dir, return_value=str(tmp_path / "config")):
        config_path = settings.user_config_path
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("check:\n  tflint: true\n")
        config = load_user_config(settings)
    assert config.check is not None
    assert config.check.tflint


def test_load_user_config_invalid_yaml(tmp_path: Path):
    settings = _make_settings(tmp_path)
    with patch(_patch_user_config_dir, return_value=str(tmp_path / "config")):
        config_path = settings.user_config_path
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("check:\n  tflint: [invalid\n")
        config = load_user_config(settings)
    assert config.check is None


def test_user_config_model():
    config = TfDoUserConfig(check=CheckConfig(tflint=True))
    assert config.check is not None
    assert config.check.tflint
    empty = TfDoUserConfig()
    assert empty.check is None
