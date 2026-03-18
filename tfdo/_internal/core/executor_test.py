from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ask_shell.shell import AbortRetryError, ShellRun
from typer.testing import CliRunner

from tfdo._internal.core import executor
from tfdo._internal.core.executor import (
    _build_init_command,
    _clean_terraform_cache,
    _init_should_retry,
    _is_checksum_error,
    _is_transient,
    init,
)
from tfdo._internal.models import InitInput
from tfdo._internal.settings import TfDoSettings

module_name = init.__module__
runner = CliRunner()


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
    with patch(f"{module_name}.{executor.run_and_wait.__name__}", return_value=run):
        result = init(InitInput(settings=settings))
    assert result.exit_code == 0
    assert result.attempts_used == 1


def test_init_extra_args_forwarded(tmp_path: Path):
    settings = _make_settings(tmp_path)
    run = _mock_run(exit_code=0, attempt=1)
    with patch(f"{module_name}.{executor.run_and_wait.__name__}", return_value=run) as mock_raw:
        init(InitInput(settings=settings, extra_args=["-upgrade", "-input=false"]))
    cmd = mock_raw.call_args[0][0]
    assert "-upgrade" in cmd
    assert "-input=false" in cmd


def test_init_cmd_via_cli(tmp_path: Path):
    from tfdo._internal.core import cmd_init  # noqa: F401
    from tfdo._internal.typer_app import app

    run = _mock_run(exit_code=0, attempt=1)
    with patch(f"{module_name}.{executor.run_and_wait.__name__}", return_value=run):
        result = runner.invoke(app, ["--work-dir", str(tmp_path), "init"])
    assert result.exit_code == 0
