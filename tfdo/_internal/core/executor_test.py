from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ask_shell.shell import AbortRetryError, ShellRun
from typer.testing import CliRunner

from tfdo._internal.core import executor
from tfdo._internal.core.executor import (
    _build_init_command,
    _build_lifecycle_command,
    _clean_terraform_cache,
    _init_should_retry,
    _is_checksum_error,
    _is_transient,
    _needs_init,
    apply,
    destroy,
    init,
    plan,
)
from tfdo._internal.models import ApplyInput, DestroyInput, InitInput, InitMode, PlanInput
from tfdo._internal.settings import TfDoSettings

module_name = init.__module__
runner = CliRunner()
_patch_run = f"{module_name}.{executor.run_and_wait.__name__}"


def _make_settings(tmp_path: Path) -> TfDoSettings:
    return TfDoSettings.for_testing(tmp_path, work_dir=tmp_path)


def _mock_run(exit_code: int = 0, stderr: str = "", attempt: int = 1, cwd: Path | None = None) -> MagicMock:
    run = MagicMock(spec=ShellRun)
    run.exit_code = exit_code
    run.stderr = stderr
    run.current_attempt = attempt
    run.config = MagicMock()
    run.config.cwd = cwd or Path("/tmp")
    return run


# --- init tests ---


def test_transient_and_checksum_detection():
    assert _is_transient("Error: connection reset by peer")
    assert _is_transient("TLS handshake timeout occurred")
    assert not _is_transient("syntax error in main.tf")
    assert _is_checksum_error("provider checksum verification failed")
    assert _is_checksum_error("locked provider registry.terraform.io/hashicorp/aws")
    assert not _is_checksum_error("syntax error in main.tf")


def test_init_should_retry_transient():
    run = _mock_run(exit_code=1, stderr="connection reset by peer")
    assert _init_should_retry(run)


def test_init_should_retry_checksum_cleans_cache(tmp_path: Path):
    providers = tmp_path / ".terraform" / "providers"
    modules = tmp_path / ".terraform" / "modules"
    providers.mkdir(parents=True)
    modules.mkdir(parents=True)

    run = _mock_run(exit_code=1, stderr="checksum list has changed", cwd=tmp_path)
    assert _init_should_retry(run)
    assert not providers.exists()
    assert not modules.exists()


def test_init_should_retry_permanent_error_aborts():
    run = _mock_run(exit_code=1, stderr="Error: Invalid HCL syntax")
    with pytest.raises(AbortRetryError, match="permanent error"):
        _init_should_retry(run)


def test_clean_terraform_cache(tmp_path: Path):
    providers = tmp_path / ".terraform" / "providers"
    providers.mkdir(parents=True)
    assert _clean_terraform_cache(tmp_path)
    assert not providers.exists()
    assert not _clean_terraform_cache(tmp_path)


def test_build_init_command():
    assert _build_init_command("terraform", []) == "terraform init"
    assert _build_init_command("tofu", ["-upgrade", "-input=false"]) == "tofu init -upgrade -input=false"


def test_init_success(tmp_path: Path):
    settings = _make_settings(tmp_path)
    run = _mock_run(exit_code=0, attempt=1)
    with patch(_patch_run, return_value=run):
        result = init(InitInput(settings=settings))
    assert result.exit_code == 0
    assert result.attempts_used == 1


def test_init_extra_args_forwarded(tmp_path: Path):
    settings = _make_settings(tmp_path)
    run = _mock_run(exit_code=0, attempt=1)
    with patch(_patch_run, return_value=run) as mock_raw:
        init(InitInput(settings=settings, extra_args=["-upgrade", "-input=false"]))
    cmd = mock_raw.call_args[0][0]
    assert "-upgrade" in cmd
    assert "-input=false" in cmd


def test_init_cmd_via_cli(tmp_path: Path):
    from tfdo._internal.core import cmd_init  # noqa: F401
    from tfdo._internal.typer_app import app

    run = _mock_run(exit_code=0, attempt=1)
    with patch(_patch_run, return_value=run):
        result = runner.invoke(app, ["--work-dir", str(tmp_path), "init"])
    assert result.exit_code == 0


# --- lifecycle command building ---


def test_build_lifecycle_command():
    assert _build_lifecycle_command("terraform", "plan", None, []) == "terraform plan"
    assert _build_lifecycle_command("tofu", "apply", Path("dev.tfvars"), ["-auto-approve"]) == (
        "tofu apply -var-file=dev.tfvars -auto-approve"
    )


# --- plan tests ---


def test_plan_success(tmp_path: Path):
    settings = _make_settings(tmp_path)
    run = _mock_run(exit_code=0)
    with patch(_patch_run, return_value=run) as mock_raw:
        result = plan(PlanInput(settings=settings))
    assert result.exit_code == 0
    assert "terraform plan" in mock_raw.call_args[0][0]


def test_plan_exit_code_2_changes_detected(tmp_path: Path):
    settings = _make_settings(tmp_path)
    run = _mock_run(exit_code=2)
    with patch(_patch_run, return_value=run):
        result = plan(PlanInput(settings=settings))
    assert result.exit_code == 2


def test_plan_flags_forwarded(tmp_path: Path):
    settings = _make_settings(tmp_path)
    run = _mock_run(exit_code=0)
    with patch(_patch_run, return_value=run) as mock_raw:
        plan(PlanInput(settings=settings, out=Path("tfplan"), json_output=True, var_file=Path("dev.tfvars")))
    cmd = mock_raw.call_args[0][0]
    assert "-var-file=dev.tfvars" in cmd
    assert "-out=tfplan" in cmd
    assert "-json" in cmd


def test_plan_always_init_aborts_on_failure(tmp_path: Path):
    settings = _make_settings(tmp_path)
    init_run = _mock_run(exit_code=1, attempt=1)
    with patch(_patch_run, return_value=init_run) as mock_raw:
        result = plan(PlanInput(settings=settings, init_mode=InitMode.ALWAYS))
    assert result.exit_code == 1
    mock_raw.assert_called_once()
    assert "init" in mock_raw.call_args[0][0]


# --- apply tests ---


def test_apply_auto_approve(tmp_path: Path):
    settings = _make_settings(tmp_path)
    run = _mock_run(exit_code=0)
    with patch(_patch_run, return_value=run) as mock_raw:
        result = apply(ApplyInput(settings=settings, auto_approve=True, var_file=Path("prod.tfvars")))
    assert result.exit_code == 0
    cmd = mock_raw.call_args[0][0]
    assert "-auto-approve" in cmd
    assert "-var-file=prod.tfvars" in cmd


# --- destroy tests ---


def test_destroy_auto_approve(tmp_path: Path):
    settings = _make_settings(tmp_path)
    run = _mock_run(exit_code=0)
    with patch(_patch_run, return_value=run) as mock_raw:
        result = destroy(DestroyInput(settings=settings, auto_approve=True))
    assert result.exit_code == 0
    cmd = mock_raw.call_args[0][0]
    assert "terraform destroy" in cmd
    assert "-auto-approve" in cmd


def test_lifecycle_always_init_then_command(tmp_path: Path):
    settings = _make_settings(tmp_path)
    init_run = _mock_run(exit_code=0, attempt=1)
    apply_run = _mock_run(exit_code=0)
    with patch(_patch_run, side_effect=[init_run, apply_run]) as mock_raw:
        result = apply(ApplyInput(settings=settings, init_mode=InitMode.ALWAYS, auto_approve=True))
    assert result.exit_code == 0
    assert mock_raw.call_count == 2
    cmds = [c[0][0] for c in mock_raw.call_args_list]
    assert "init" in cmds[0]
    assert "apply" in cmds[1]


# --- init mode tests ---


def test_needs_init_detection():
    assert _needs_init('Error: Could not load plugin\n\nPlease run "terraform init"')
    assert _needs_init("Error: Missing required provider")
    assert _needs_init("Error: Backend initialization required")
    assert _needs_init("Error: Module not installed")
    assert not _needs_init("Error: Invalid HCL syntax")


def test_auto_init_retries_on_init_needed_error(tmp_path: Path):
    settings = _make_settings(tmp_path)
    fail_run = _mock_run(exit_code=1, stderr='Plugin not found. Please run "terraform init"')
    init_run = _mock_run(exit_code=0, attempt=1)
    success_run = _mock_run(exit_code=0)
    with patch(_patch_run, side_effect=[fail_run, init_run, success_run]) as mock_raw:
        result = plan(PlanInput(settings=settings))
    assert result.exit_code == 0
    assert mock_raw.call_count == 3
    cmds = [c[0][0] for c in mock_raw.call_args_list]
    assert "plan" in cmds[0]
    assert "init" in cmds[1]
    assert "plan" in cmds[2]


def test_auto_init_skips_when_no_init_pattern(tmp_path: Path):
    settings = _make_settings(tmp_path)
    fail_run = _mock_run(exit_code=1, stderr="Error: Invalid resource type")
    with patch(_patch_run, return_value=fail_run) as mock_raw:
        result = plan(PlanInput(settings=settings))
    assert result.exit_code == 1
    mock_raw.assert_called_once()


def test_never_init_mode_skips_init(tmp_path: Path):
    settings = _make_settings(tmp_path)
    fail_run = _mock_run(exit_code=1, stderr='Please run "terraform init"')
    with patch(_patch_run, return_value=fail_run) as mock_raw:
        result = plan(PlanInput(settings=settings, init_mode=InitMode.NEVER))
    assert result.exit_code == 1
    mock_raw.assert_called_once()


# --- CLI integration ---


def test_plan_cmd_via_cli(tmp_path: Path):
    from tfdo._internal.core import cmd_plan  # noqa: F401
    from tfdo._internal.typer_app import app

    run = _mock_run(exit_code=0)
    with patch(_patch_run, return_value=run):
        result = runner.invoke(app, ["--work-dir", str(tmp_path), "plan"])
    assert result.exit_code == 0


def test_apply_cmd_via_cli(tmp_path: Path):
    from tfdo._internal.core import cmd_apply  # noqa: F401
    from tfdo._internal.typer_app import app

    run = _mock_run(exit_code=0)
    with patch(_patch_run, return_value=run):
        result = runner.invoke(app, ["--work-dir", str(tmp_path), "apply", "--auto-approve"])
    assert result.exit_code == 0


def test_destroy_cmd_via_cli(tmp_path: Path):
    from tfdo._internal.core import cmd_destroy  # noqa: F401
    from tfdo._internal.typer_app import app

    run = _mock_run(exit_code=0)
    with patch(_patch_run, return_value=run):
        result = runner.invoke(app, ["--work-dir", str(tmp_path), "destroy", "--auto-approve"])
    assert result.exit_code == 0
