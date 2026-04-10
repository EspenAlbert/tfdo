from __future__ import annotations

import threading
from pathlib import Path

from tfdo._internal.config.enums import LifecycleCommand, LifecycleEvent
from tfdo._internal.hooks.execution import HookContext, _hook_env, lifecycle_events, run_after_hooks, run_before_hooks
from tfdo._internal.hooks.models import ExitEvent, HookInput
from tfdo._internal.hooks.registry import HookRegistry, HookSource


def _make_ctx(tmp_path: Path) -> HookContext:
    return HookContext(run_dir=tmp_path, command="plan")


def test_before_hook_exit_event_returns_false(tmp_path: Path):
    registry = HookRegistry()
    registry.register(
        "abort",
        [LifecycleEvent.PLAN_BEFORE],
        lambda inp: ExitEvent(reason="stop"),
        priority=100,
        source=HookSource.LOCAL,
    )

    assert not run_before_hooks(registry, LifecycleEvent.PLAN_BEFORE, _make_ctx(tmp_path))


def test_before_hook_exception_returns_false(tmp_path: Path):
    def _raise(inp: HookInput) -> None:
        raise RuntimeError("boom")

    registry = HookRegistry()
    registry.register("boom", [LifecycleEvent.PLAN_BEFORE], _raise, priority=100, source=HookSource.LOCAL)
    assert not run_before_hooks(registry, LifecycleEvent.PLAN_BEFORE, _make_ctx(tmp_path))


def test_before_hook_success_returns_true(tmp_path: Path):
    calls: list[str] = []
    registry = HookRegistry()
    registry.register(
        "ok", [LifecycleEvent.PLAN_BEFORE], lambda inp: calls.append("ok"), priority=100, source=HookSource.LOCAL
    )

    assert run_before_hooks(registry, LifecycleEvent.PLAN_BEFORE, _make_ctx(tmp_path))
    assert calls == ["ok"]


def test_after_hook_failure_continues(tmp_path: Path):
    calls: list[str] = []

    def _raise(inp: HookInput) -> None:
        raise RuntimeError("boom")

    registry = HookRegistry()
    registry.register("fail", [LifecycleEvent.PLAN_AFTER], _raise, priority=50, source=HookSource.LOCAL)
    registry.register(
        "ok", [LifecycleEvent.PLAN_AFTER], lambda inp: calls.append("ok"), priority=100, source=HookSource.LOCAL
    )

    run_after_hooks(registry, LifecycleEvent.PLAN_AFTER, _make_ctx(tmp_path))
    assert calls == ["ok"]


def test_contextvar_isolation_across_threads():
    results: dict[str, dict[str, str]] = {}

    def _set_and_read(name: str, value: str) -> None:
        _hook_env.set({name: value})
        threading.Event().wait(0.05)
        results[name] = _hook_env.get()

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


def test_hook_context_skips_none_fields(tmp_path: Path):
    ctx = HookContext(run_dir=tmp_path, command="plan")
    hook_input = ctx.to_hook_input(LifecycleEvent.PLAN_BEFORE)
    env = hook_input.env_vars
    assert "TFDO_CMD_DIR" not in env
    assert "TFDO_RUN_STATE_DIR" not in env
    assert env["TFDO_RUN_DIR"] == str(tmp_path)
