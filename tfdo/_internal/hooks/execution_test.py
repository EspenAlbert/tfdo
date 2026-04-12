from __future__ import annotations

import threading
from pathlib import Path

import pytest

from tfdo._internal.config.enums import HookOnError, LifecycleCommand, LifecycleEvent
from tfdo._internal.hooks.execution import HookContext, get_hook_env, lifecycle_events, run_hooks, set_hook_env
from tfdo._internal.hooks.models import ExitEvent, HookAbortError, HookInput
from tfdo._internal.hooks.registry import HookRegistry, HookSource


def _make_ctx(tmp_path: Path) -> HookContext:
    return HookContext(run_dir=tmp_path, command="plan")


def test_hook_exit_event_raises(tmp_path: Path):
    registry = HookRegistry()
    registry.register(
        "abort",
        [LifecycleEvent.PLAN_BEFORE],
        lambda inp: ExitEvent(reason="stop"),
        priority=100,
        source=HookSource.LOCAL,
    )

    with pytest.raises(HookAbortError, match="stop") as exc_info:
        run_hooks(registry, LifecycleEvent.PLAN_BEFORE, _make_ctx(tmp_path))
    assert exc_info.value.exit_event.reason == "stop"


def test_hook_exception_raises_abort_error(tmp_path: Path):
    def _raise(inp: HookInput) -> None:
        raise RuntimeError("boom")

    registry = HookRegistry()
    registry.register("boom", [LifecycleEvent.PLAN_BEFORE], _raise, priority=100, source=HookSource.LOCAL)

    with pytest.raises(HookAbortError, match="boom"):
        run_hooks(registry, LifecycleEvent.PLAN_BEFORE, _make_ctx(tmp_path))


def test_hook_success_no_exception(tmp_path: Path):
    calls: list[str] = []
    registry = HookRegistry()
    registry.register(
        "ok", [LifecycleEvent.PLAN_BEFORE], lambda inp: calls.append("ok"), priority=100, source=HookSource.LOCAL
    )

    run_hooks(registry, LifecycleEvent.PLAN_BEFORE, _make_ctx(tmp_path))
    assert calls == ["ok"]


def test_contextvar_isolation_across_threads():
    results: dict[str, dict[str, str]] = {}

    def _set_and_read(name: str, value: str) -> None:
        set_hook_env({name: value})
        threading.Event().wait(0.05)
        results[name] = get_hook_env()

    t1 = threading.Thread(target=_set_and_read, args=("t1", "v1"))
    t2 = threading.Thread(target=_set_and_read, args=("t2", "v2"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results["t1"] == {"t1": "v1"}
    assert results["t2"] == {"t2": "v2"}


def test_lifecycle_events_mapping():
    before, after = lifecycle_events(LifecycleCommand.PLAN)
    assert before == LifecycleEvent.PLAN_BEFORE
    assert after == LifecycleEvent.PLAN_AFTER

    before, after = lifecycle_events(LifecycleCommand.APPLY)
    assert before == LifecycleEvent.APPLY_BEFORE
    assert after == LifecycleEvent.APPLY_AFTER


def test_warn_mode_exception_logs_and_continues(tmp_path: Path, caplog):
    calls: list[str] = []

    def _raise(inp: HookInput) -> None:
        raise RuntimeError("boom")

    registry = HookRegistry()
    registry.register(
        "fail", [LifecycleEvent.PLAN_BEFORE], _raise, priority=50, source=HookSource.LOCAL, on_error=HookOnError.WARN
    )
    registry.register(
        "ok",
        [LifecycleEvent.PLAN_BEFORE],
        lambda inp: calls.append("ok"),
        priority=100,
        source=HookSource.LOCAL,
        on_error=HookOnError.WARN,
    )

    run_hooks(registry, LifecycleEvent.PLAN_BEFORE, _make_ctx(tmp_path))
    assert calls == ["ok"]
    assert "hook 'fail' failed: boom" in caplog.text


def test_warn_mode_exit_event_logs_and_continues(tmp_path: Path, caplog):
    calls: list[str] = []
    registry = HookRegistry()
    registry.register(
        "exit",
        [LifecycleEvent.PLAN_BEFORE],
        lambda inp: ExitEvent(reason="soft-stop"),
        priority=50,
        source=HookSource.LOCAL,
        on_error=HookOnError.WARN,
    )
    registry.register(
        "ok",
        [LifecycleEvent.PLAN_BEFORE],
        lambda inp: calls.append("ok"),
        priority=100,
        source=HookSource.LOCAL,
        on_error=HookOnError.WARN,
    )

    run_hooks(registry, LifecycleEvent.PLAN_BEFORE, _make_ctx(tmp_path))
    assert calls == ["ok"]
    assert "soft-stop" in caplog.text


def test_hook_context_skips_none_fields(tmp_path: Path):
    ctx = HookContext(run_dir=tmp_path, command="plan")
    hook_input = ctx.to_hook_input(LifecycleEvent.PLAN_BEFORE)
    env = hook_input.env_vars
    assert "TFDO_CMD_DIR" not in env
    assert "TFDO_RUN_STATE_DIR" not in env
    assert env["TFDO_RUN_DIR"] == str(tmp_path)
