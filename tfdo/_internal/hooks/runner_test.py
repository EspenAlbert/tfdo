from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from ask_shell.shell import run_and_wait

from tfdo._internal.config.config_model import HookConfig
from tfdo._internal.config.enums import LifecycleEvent
from tfdo._internal.hooks.models import ExitEvent, HookInput
from tfdo._internal.hooks.runner import LocalHookRunner


def _make_input() -> HookInput:
    return HookInput(env_vars={"TFDO_COMMAND": "plan", "TFDO_HOOK_POINT": "plan_before", "TFDO_RUN_DIR": "/tmp/rd"})


def test_wrap_cmd_passes_env_and_timeout(tmp_path: Path):
    config = HookConfig(
        name="test-cmd", cmd="echo hello", lifecycle_events=[LifecycleEvent.PLAN_BEFORE], timeout_seconds=42
    )
    runner = LocalHookRunner(tmp_path)

    runner_module = LocalHookRunner.__module__
    with patch(f"{runner_module}.{run_and_wait.__name__}") as mock_raw:
        fn = runner.wrap(config)
        result = fn(_make_input())

    assert result is None
    mock_raw.assert_called_once()
    call_kwargs = mock_raw.call_args
    assert call_kwargs[0][0] == "echo hello"
    assert call_kwargs[1]["timeout"] == 42
    assert call_kwargs[1]["cwd"] == tmp_path
    assert "TFDO_COMMAND" in call_kwargs[1]["env"]


def test_wrap_py_locate_zero_arg(tmp_path: Path):
    config = HookConfig(name="test-py", py_locate="os.getcwd", lifecycle_events=[LifecycleEvent.PLAN_BEFORE])
    runner = LocalHookRunner(tmp_path)
    fn = runner.wrap(config)
    result = fn(_make_input())
    assert result is None


def test_wrap_py_locate_one_arg_returns_exit_event(tmp_path: Path):
    config = HookConfig(
        name="test-py",
        py_locate="tfdo._internal.hooks.runner_test._exit_hook",
        lifecycle_events=[LifecycleEvent.PLAN_BEFORE],
    )
    runner = LocalHookRunner(tmp_path)
    fn = runner.wrap(config)
    result = fn(_make_input())
    assert isinstance(result, ExitEvent)
    assert result.reason == "test-abort"


def test_wrap_py_locate_invalid_path_raises(tmp_path: Path):
    config = HookConfig(name="bad", py_locate="nonexistent.module.func", lifecycle_events=[LifecycleEvent.PLAN_BEFORE])
    runner = LocalHookRunner(tmp_path)
    with pytest.raises(ValueError, match="not found"):
        runner.wrap(config)


def _exit_hook(hook_input: HookInput) -> ExitEvent:
    return ExitEvent(reason="test-abort")
