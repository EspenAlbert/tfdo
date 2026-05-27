from pathlib import Path
from shutil import which
from unittest.mock import MagicMock, patch

import pytest
from ask_shell.shell import AbortRetryError, ShellRun
from typer.testing import CliRunner

from tfdo._internal.core import apply_logic, binary, plan_logic, plan_subprocess, terraform_init
from tfdo._internal.core.executor import (
    _parse_tf_outputs,
    apply,
    destroy,
    output_json,
    plan,
)
from tfdo._internal.core.lifecycle_init_retry import (
    init_input_for_output_retry,
    is_backend_changed,
    needs_init,
)
from tfdo._internal.core.lifecycle_shell import build_lifecycle_command
from tfdo._internal.core.plan_subprocess import run_streaming_plan
from tfdo._internal.core.terraform_init import (
    _clean_terraform_cache,
    _is_checksum_error,
    _is_transient,
    init,
    terraform_init_should_retry,
)
from tfdo._internal.models import (
    ApplyInput,
    ApplyResult,
    DestroyInput,
    DestroyResult,
    InitInput,
    InitMode,
    InitResult,
    OutputInput,
    PlanInput,
    PlanResult,
)
from tfdo._internal.output.plan_artifacts import plan_bin_path
from tfdo._internal.settings import InteractiveMode, TfDoSettings

runner = CliRunner()
_patch_init_run = "tfdo._internal.core.terraform_init.run_and_wait"
_patch_lifecycle_run = "tfdo._internal.core.lifecycle_shell.run_and_wait"
_patch_plan_run = "tfdo._internal.core.plan_subprocess.run_and_wait"
_patch_output_run = "tfdo._internal.core.executor.run_and_wait"
_patch_which = f"{binary.resolve_binary.__module__}.{which.__name__}"
_patch_plan_and_render = f"{plan_logic.__name__}.{plan_logic.plan_and_render.__name__}"


def _make_settings(
    tmp_path: Path,
    interactive: InteractiveMode = InteractiveMode.ALWAYS,
    tf_version: str | None = None,
) -> TfDoSettings:
    return TfDoSettings.for_testing(tmp_path, work_dir=tmp_path, interactive=interactive, tf_version=tf_version)


def _mock_run(
    exit_code: int = 0, stderr: str = "", stdout: str = "", attempt: int = 1, cwd: Path | None = None
) -> MagicMock:
    run = MagicMock(spec=ShellRun)
    run.exit_code = exit_code
    run.stderr = stderr
    run.stdout = stdout
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
    assert terraform_init_should_retry(run)


def test_init_should_retry_checksum_cleans_cache(tmp_path: Path):
    providers = tmp_path / ".terraform" / "providers"
    modules = tmp_path / ".terraform" / "modules"
    providers.mkdir(parents=True)
    modules.mkdir(parents=True)

    run = _mock_run(exit_code=1, stderr="checksum list has changed", cwd=tmp_path)
    assert terraform_init_should_retry(run)
    assert not providers.exists()
    assert not modules.exists()


def test_init_should_retry_permanent_error_aborts():
    run = _mock_run(exit_code=1, stderr="Error: Invalid HCL syntax")
    with pytest.raises(AbortRetryError, match="permanent error"):
        terraform_init_should_retry(run)


def test_clean_terraform_cache(tmp_path: Path):
    providers = tmp_path / ".terraform" / "providers"
    providers.mkdir(parents=True)
    assert _clean_terraform_cache(tmp_path)
    assert not providers.exists()
    assert not _clean_terraform_cache(tmp_path)


def test_build_init_command():
    assert terraform_init._build_init_command("terraform", [], []) == "terraform init"
    assert (
        terraform_init._build_init_command("tofu", [], ["-upgrade", "-input=false"])
        == "tofu init -upgrade -input=false"
    )
    assert (
        terraform_init._build_init_command("mise x terraform@1.14 -- terraform", [], [])
        == "mise x terraform@1.14 -- terraform init"
    )


def test_build_init_command_backend_args_before_extra():
    backend = ["-backend-config=bucket=b", "-backend-config=key=k"]
    extra = ["-upgrade"]
    result = terraform_init._build_init_command("terraform", backend, extra)
    assert result == "terraform init -backend-config=bucket=b -backend-config=key=k -upgrade"


def test_init_success(tmp_path: Path):
    settings = _make_settings(tmp_path)
    run = _mock_run(exit_code=0, attempt=1)
    with patch(_patch_init_run, return_value=run):
        result = init(InitInput(settings=settings))
    assert result.exit_code == 0
    assert result.attempts_used == 1
    assert result.stderr is None


def test_init_failure_includes_stderr(tmp_path: Path):
    settings = _make_settings(tmp_path)
    run = _mock_run(exit_code=1, stderr="Error: provider install failed\n", attempt=1)
    with patch(_patch_init_run, return_value=run):
        result = init(InitInput(settings=settings))
    assert result.exit_code == 1
    assert result.stderr == "Error: provider install failed"


def test_init_extra_args_forwarded(tmp_path: Path):
    settings = _make_settings(tmp_path)
    run = _mock_run(exit_code=0, attempt=1)
    with patch(_patch_init_run, return_value=run) as mock_raw:
        init(InitInput(settings=settings, extra_args=["-upgrade", "-input=false"]))
    cmd = mock_raw.call_args[0][0]
    assert "-upgrade" in cmd
    assert "-input=false" in cmd


def test_init_cmd_via_cli(tmp_path: Path):
    from tfdo._internal.core import cmd_init  # noqa: F401
    from tfdo._internal.typer_app import app

    run = _mock_run(exit_code=0, attempt=1)
    with patch(_patch_init_run, return_value=run):
        result = runner.invoke(app, ["--work-dir", str(tmp_path), "init"])
    assert result.exit_code == 0


# --- lifecycle command building ---


def test_build_lifecycle_command():
    assert build_lifecycle_command("terraform", "plan", None, []) == "terraform plan"
    assert build_lifecycle_command("tofu", "apply", Path("dev.tfvars"), ["-auto-approve"]) == (
        "tofu apply -var-file=dev.tfvars -auto-approve"
    )


# --- plan tests ---


def test_run_streaming_plan_success(tmp_path: Path):
    settings = _make_settings(tmp_path)
    run = _mock_run(exit_code=0)
    with patch(_patch_plan_run, return_value=run) as mock_raw:
        result = run_streaming_plan(PlanInput(settings=settings))
    assert result.exit_code == 0
    cmd = mock_raw.call_args[0][0]
    assert "terraform plan" in cmd
    assert "-json" in cmd
    assert f"-out={plan_bin_path(tmp_path)}" in cmd


def test_lifecycle_result_captures_stdout_stderr(tmp_path: Path):
    settings = _make_settings(tmp_path)
    run = _mock_run(exit_code=0, stdout="Plan: 2 to add", stderr="Warning: deprecated")
    with patch(_patch_plan_run, return_value=run):
        result = run_streaming_plan(PlanInput(settings=settings))
    assert result.stderr == "Warning: deprecated"


def test_init_result_captures_stdout(tmp_path: Path):
    settings = _make_settings(tmp_path)
    run = _mock_run(exit_code=0, stdout="Initializing provider plugins...", attempt=1)
    with patch(_patch_init_run, return_value=run):
        result = init(InitInput(settings=settings))
    assert result.stdout == "Initializing provider plugins..."


def test_plan_exit_code_2_changes_detected(tmp_path: Path):
    settings = _make_settings(tmp_path)
    with patch.object(plan_logic, "run_plan", return_value=PlanResult(exit_code=2)):
        result = plan(PlanInput(settings=settings))
    assert result.exit_code == 2


def test_plan_flags_forwarded(tmp_path: Path):
    settings = _make_settings(tmp_path)
    run = _mock_run(exit_code=0)
    with patch(_patch_plan_run, return_value=run) as mock_raw:
        run_streaming_plan(PlanInput(settings=settings, var_file=Path("dev.tfvars")))
    cmd = mock_raw.call_args[0][0]
    assert "-var-file=dev.tfvars" in cmd
    assert f"-out={plan_bin_path(tmp_path)}" in cmd
    assert "-json" in cmd


def test_plan_always_init_aborts_on_failure(tmp_path: Path):
    settings = _make_settings(tmp_path)
    init_run = _mock_run(exit_code=1, attempt=1)
    with patch(_patch_init_run, return_value=init_run) as mock_raw:
        result = run_streaming_plan(PlanInput(settings=settings, init_mode=InitMode.ALWAYS))
    assert result.exit_code == 1
    mock_raw.assert_called_once()
    assert "init" in mock_raw.call_args[0][0]


# --- apply tests ---


def test_apply_auto_approve(tmp_path: Path):
    settings = _make_settings(tmp_path)
    run = _mock_run(exit_code=0)
    bin_path = plan_bin_path(tmp_path)
    bin_path.parent.mkdir(parents=True, exist_ok=True)
    bin_path.write_bytes(b"")
    with (
        patch(_patch_plan_and_render, return_value=PlanResult(exit_code=0)),
        patch(_patch_lifecycle_run, return_value=run) as mock_raw,
    ):
        result = apply(ApplyInput(settings=settings, auto_approve=True, var_file=Path("prod.tfvars")))
    assert result.exit_code == 0
    cmd = mock_raw.call_args[0][0]
    assert "-auto-approve" in cmd
    assert str(bin_path) in cmd
    assert "-var-file=prod.tfvars" in cmd


# --- destroy tests ---


def test_destroy_auto_approve(tmp_path: Path):
    settings = _make_settings(tmp_path)
    run = _mock_run(exit_code=0)
    bin_path = plan_bin_path(tmp_path)
    bin_path.parent.mkdir(parents=True, exist_ok=True)
    bin_path.write_bytes(b"")
    with (
        patch(_patch_plan_and_render, return_value=PlanResult(exit_code=0)),
        patch(_patch_lifecycle_run, return_value=run) as mock_raw,
    ):
        result = destroy(DestroyInput(settings=settings, auto_approve=True, var_file=Path("prod.tfvars")))
    assert result.exit_code == 0
    cmd = mock_raw.call_args[0][0]
    assert "terraform apply" in cmd
    assert "terraform destroy" not in cmd
    assert "-auto-approve" in cmd
    assert str(bin_path) in cmd
    assert "-var-file=prod.tfvars" in cmd


def test_lifecycle_always_init_then_command(tmp_path: Path):
    settings = _make_settings(tmp_path)
    init_run = _mock_run(exit_code=0, attempt=1)
    apply_run = _mock_run(exit_code=0)
    bin_path = plan_bin_path(tmp_path)
    bin_path.parent.mkdir(parents=True, exist_ok=True)
    bin_path.write_bytes(b"")
    with (
        patch(_patch_plan_and_render, return_value=PlanResult(exit_code=0)),
        patch(_patch_init_run, return_value=init_run),
        patch(_patch_lifecycle_run, return_value=apply_run) as mock_apply,
    ):
        result = apply(ApplyInput(settings=settings, init_mode=InitMode.ALWAYS, auto_approve=True))
    assert result.exit_code == 0
    assert "apply" in mock_apply.call_args[0][0]


# --- init mode tests ---


def test_needs_init_detection():
    assert needs_init('Error: Could not load plugin\n\nPlease run "terraform init"')
    assert needs_init("Error: Missing required provider")
    assert needs_init("Error: Backend initialization required")
    assert needs_init("Error: Module not installed")
    assert not needs_init("Error: Backend configuration changed")
    assert not needs_init("Error: Invalid HCL syntax")


def test_init_input_for_output_retry(tmp_path: Path):
    settings = _make_settings(tmp_path)
    base = InitInput(settings=settings, backend_args=["-backend-config=a"])
    changed = init_input_for_output_retry("Backend configuration changed", base)
    assert changed is not None
    assert "-reconfigure" in changed.extra_args
    assert changed.backend_args == base.backend_args
    assert init_input_for_output_retry("Backend initialization required", base) is base
    assert init_input_for_output_retry("Invalid HCL", base) is None


def test_auto_init_retries_on_init_needed_error(tmp_path: Path):
    settings = _make_settings(tmp_path)
    fail_run = _mock_run(exit_code=1, stderr='Plugin not found. Please run "terraform init"')
    init_run = _mock_run(exit_code=0, attempt=1)
    success_run = _mock_run(exit_code=0)
    with (
        patch(_patch_plan_run, side_effect=[fail_run, success_run]) as mock_plan,
        patch(_patch_init_run, return_value=init_run),
    ):
        result = run_streaming_plan(PlanInput(settings=settings))
    assert result.exit_code == 0
    assert mock_plan.call_count == 2
    cmds = [c[0][0] for c in mock_plan.call_args_list]
    assert "plan" in cmds[0]
    assert "plan" in cmds[1]


def test_auto_init_skips_when_no_init_pattern(tmp_path: Path):
    settings = _make_settings(tmp_path)
    fail_run = _mock_run(exit_code=1, stderr="Error: Invalid resource type")
    with patch(_patch_plan_run, return_value=fail_run) as mock_raw:
        result = run_streaming_plan(PlanInput(settings=settings))
    assert result.exit_code == 1
    mock_raw.assert_called_once()


def test_never_init_mode_skips_init(tmp_path: Path):
    settings = _make_settings(tmp_path)
    fail_run = _mock_run(exit_code=1, stderr='Please run "terraform init"')
    with patch(_patch_plan_run, return_value=fail_run) as mock_raw:
        result = run_streaming_plan(PlanInput(settings=settings, init_mode=InitMode.NEVER))
    assert result.exit_code == 1
    mock_raw.assert_called_once()


# --- CLI integration ---


def test_plan_cmd_via_cli(tmp_path: Path):
    from tfdo._internal.typer_app import app

    with patch.object(plan_logic, "run_plan", return_value=PlanResult(exit_code=0)):
        result = runner.invoke(app, ["--work-dir", str(tmp_path), "plan"])
    assert result.exit_code == 0


def test_apply_cmd_via_cli(tmp_path: Path):
    from tfdo._internal.core import cmd_apply  # noqa: F401
    from tfdo._internal.typer_app import app

    with patch.object(apply_logic, "run_apply", return_value=ApplyResult(exit_code=0)):
        result = runner.invoke(app, ["--work-dir", str(tmp_path), "apply", "--auto-approve"])
    assert result.exit_code == 0


def test_destroy_cmd_via_cli(tmp_path: Path):
    from tfdo._internal.core import (
        cmd_destroy,  # noqa: F401
        destroy_logic,
    )
    from tfdo._internal.typer_app import app

    with patch.object(destroy_logic, "run_destroy", return_value=DestroyResult(exit_code=0)):
        result = runner.invoke(app, ["--work-dir", str(tmp_path), "destroy", "--auto-approve"])
    assert result.exit_code == 0


# --- mise version selection ---


def test_init_with_tf_version(tmp_path: Path):
    settings = _make_settings(tmp_path, tf_version="1.14.0")
    run = _mock_run(exit_code=0, attempt=1)
    with patch(_patch_which, return_value="/usr/local/bin/mise"), patch(_patch_init_run, return_value=run) as mock_raw:
        result = init(InitInput(settings=settings))
    assert result.exit_code == 0
    assert mock_raw.call_args[0][0] == "mise x terraform@1.14.0 -- terraform init"


def test_plan_with_tf_version(tmp_path: Path):
    settings = _make_settings(tmp_path, tf_version="1.14.0")
    run = _mock_run(exit_code=0)
    with patch(_patch_which, return_value="/usr/local/bin/mise"), patch(_patch_plan_run, return_value=run) as mock_raw:
        result = run_streaming_plan(PlanInput(settings=settings))
    assert result.exit_code == 0
    cmd = mock_raw.call_args[0][0]
    assert cmd.startswith("mise x terraform@1.14.0 -- terraform plan")
    assert "-json" in cmd


def test_destroy_plan_adds_destroy_flag(tmp_path: Path):
    settings = _make_settings(tmp_path)
    run = _mock_run(exit_code=0)
    with patch(_patch_plan_run, return_value=run) as mock_raw:
        result = run_streaming_plan(PlanInput(settings=settings, destroy_plan=True))
    assert result.exit_code == 0
    cmd = mock_raw.call_args[0][0]
    assert " plan -destroy " in f" {cmd} "


# --- interactive / approval validation ---


def test_apply_rejects_no_approve_non_interactive(tmp_path: Path):
    settings = _make_settings(tmp_path, interactive=InteractiveMode.NEVER)
    with pytest.raises(ValueError, match="terraform apply requires approval"):
        ApplyInput(settings=settings)


def test_apply_allows_auto_approve_non_interactive(tmp_path: Path):
    settings = _make_settings(tmp_path, interactive=InteractiveMode.NEVER)
    model = ApplyInput(settings=settings, auto_approve=True)
    assert model.auto_approve


def test_destroy_rejects_no_approve_non_interactive(tmp_path: Path):
    settings = _make_settings(tmp_path, interactive=InteractiveMode.NEVER)
    with pytest.raises(ValueError, match="terraform destroy requires approval"):
        DestroyInput(settings=settings)


def test_is_interactive_modes(tmp_path: Path):
    assert _make_settings(tmp_path, interactive=InteractiveMode.ALWAYS).is_interactive
    assert not _make_settings(tmp_path, interactive=InteractiveMode.NEVER).is_interactive


def test_auto_init_uses_backend_args(tmp_path: Path):
    settings = _make_settings(tmp_path)
    backend_args = ["-backend-config=bucket=my-bucket"]
    input_model = PlanInput(settings=settings, init_backend_args=backend_args)

    init_calls: list[InitInput] = []

    def mock_init(inp: InitInput) -> InitResult:
        init_calls.append(inp)
        return InitResult(exit_code=0, attempts_used=1)

    with (
        patch.object(
            plan_subprocess,
            "_run_streaming_command",
            side_effect=[
                PlanResult(exit_code=1, stderr="terraform init is required"),
                PlanResult(exit_code=0),
            ],
        ),
        patch.object(terraform_init, "init", side_effect=mock_init),
    ):
        result = run_streaming_plan(input_model)

    assert result.exit_code == 0
    assert len(init_calls) == 1
    assert init_calls[0].backend_args == backend_args


def test_backend_changed_warns_without_auto_reconfigure(tmp_path: Path):
    """Backend configuration changed should warn, not silently auto-reconfigure."""
    settings = _make_settings(tmp_path)
    input_model = PlanInput(settings=settings, init_backend_args=["-backend-config=key=new"])

    with (
        patch.object(
            plan_subprocess,
            "_run_streaming_command",
            return_value=PlanResult(exit_code=1, stderr="Backend configuration changed"),
        ),
        patch.object(terraform_init, "init") as mock_init,
    ):
        result = run_streaming_plan(input_model)

    assert result.exit_code == 1
    mock_init.assert_not_called()


def test_is_backend_changed_detection():
    assert is_backend_changed("Error: Backend configuration changed")
    assert is_backend_changed("BACKEND CONFIGURATION CHANGED for module foo")
    assert not is_backend_changed("Error: Missing required provider")
    assert not is_backend_changed("")


# --- output_json tests ---


def test_parse_tf_outputs():
    raw = {
        "id": {"value": "abc123", "type": "string"},
        "name": {"value": "my-project", "type": "string"},
    }
    assert _parse_tf_outputs(raw) == {"id": "abc123", "name": "my-project"}
    assert _parse_tf_outputs({}) == {}


def test_output_json_success(tmp_path: Path):
    settings = _make_settings(tmp_path)
    tf_output = '{"id": {"value": "abc123", "type": "string"}}'
    run = _mock_run(exit_code=0, stdout=tf_output)
    run.parse_output.return_value = {"id": {"value": "abc123", "type": "string"}}
    with patch(_patch_output_run, return_value=run) as mock_run:
        result = output_json(OutputInput(settings=settings))
    assert result.exit_code == 0
    assert result.outputs == {"id": "abc123"}
    assert mock_run.call_args.kwargs["ansi_content"] is False


def test_output_json_failure(tmp_path: Path):
    settings = _make_settings(tmp_path)
    run = _mock_run(exit_code=1, stderr="No state file found")
    with patch(_patch_output_run, return_value=run):
        result = output_json(OutputInput(settings=settings))
    assert result.exit_code == 1


def test_output_json_with_state_path(tmp_path: Path):
    settings = _make_settings(tmp_path)
    tf_output = '{"id": {"value": "abc123", "type": "string"}}'
    run = _mock_run(exit_code=0, stdout=tf_output)
    run.parse_output.return_value = {"id": {"value": "abc123", "type": "string"}}
    with patch(_patch_output_run, return_value=run) as mock_raw:
        output_json(OutputInput(settings=settings, state=Path("custom.tfstate")))
    cmd = mock_raw.call_args[0][0]
    assert "-state=custom.tfstate" in cmd


def test_output_json_parses_bracketed_true_tokens(tmp_path: Path):
    settings = _make_settings(tmp_path)
    tf_output = '{"masked": {"value": [true], "type": "list(bool)", "sensitive": true}}'
    run = _mock_run(exit_code=0, stdout=tf_output)
    run.parse_output.return_value = {"masked": {"value": [True], "type": "list(bool)", "sensitive": True}}
    with patch(_patch_output_run, return_value=run):
        result = output_json(OutputInput(settings=settings))
    assert result.exit_code == 0
    assert "[true]" in tf_output
