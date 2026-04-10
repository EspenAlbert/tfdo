from __future__ import annotations

from tfdo._internal.config.config_model import HookConfig
from tfdo._internal.config.enums import LifecycleEvent
from tfdo._internal.hooks.models import HookInput, HookSource
from tfdo._internal.hooks.registry import HookRegistry


def _noop(hook_input: HookInput) -> None:
    return None


def test_get_hooks_sorted_by_priority_then_name():
    registry = HookRegistry()
    registry.register("c-hook", [LifecycleEvent.PLAN_BEFORE], _noop, priority=100, source=HookSource.LOCAL)
    registry.register("a-hook", [LifecycleEvent.PLAN_BEFORE], _noop, priority=100, source=HookSource.LOCAL)
    registry.register("b-hook", [LifecycleEvent.PLAN_BEFORE], _noop, priority=50, source=HookSource.INTERNAL)

    hooks = registry.get_hooks(LifecycleEvent.PLAN_BEFORE)
    names = [h.name for h in hooks]
    assert names == ["b-hook", "a-hook", "c-hook"]


def test_register_to_multiple_events():
    registry = HookRegistry()
    registry.register(
        "multi", [LifecycleEvent.PLAN_BEFORE, LifecycleEvent.APPLY_BEFORE], _noop, priority=100, source=HookSource.LOCAL
    )

    assert len(registry.get_hooks(LifecycleEvent.PLAN_BEFORE)) == 1
    assert len(registry.get_hooks(LifecycleEvent.APPLY_BEFORE)) == 1
    assert len(registry.get_hooks(LifecycleEvent.INIT_BEFORE)) == 0


def test_from_hook_configs(tmp_path):
    configs = [
        HookConfig(name="low-pri", py_locate="os.getcwd", lifecycle_events=[LifecycleEvent.PLAN_BEFORE], priority=100),
        HookConfig(name="high-pri", py_locate="os.getcwd", lifecycle_events=[LifecycleEvent.PLAN_BEFORE], priority=50),
    ]
    from tfdo._internal.hooks.runner import LocalHookRunner

    runner = LocalHookRunner(tmp_path)
    registry = HookRegistry.from_hook_configs(configs, runner)
    hooks = registry.get_hooks(LifecycleEvent.PLAN_BEFORE)
    assert [h.name for h in hooks] == ["high-pri", "low-pri"]
