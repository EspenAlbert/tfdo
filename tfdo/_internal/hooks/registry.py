from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Callable

from pydantic import BaseModel

from tfdo._internal.config.enums import LifecycleEvent
from tfdo._internal.hooks.models import HookEffect, HookInput, HookSource

if TYPE_CHECKING:
    from tfdo._internal.config.config_model import HookConfig
    from tfdo._internal.hooks.runner import LocalHookRunner

logger = logging.getLogger(__name__)


class RegisteredHook(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    name: str
    source: HookSource
    priority: int
    fn: Callable[[HookInput], HookEffect | None]


class HookRegistry:
    def __init__(self) -> None:
        self._hooks: dict[LifecycleEvent, list[RegisteredHook]] = defaultdict(list)

    def register(
        self,
        name: str,
        events: list[LifecycleEvent],
        fn: Callable[[HookInput], HookEffect | None],
        priority: int,
        source: HookSource,
    ) -> None:
        hook = RegisteredHook(name=name, source=source, priority=priority, fn=fn)
        for event in events:
            self._hooks[event].append(hook)

    def get_hooks(self, event: LifecycleEvent) -> list[RegisteredHook]:
        return sorted(self._hooks.get(event, []), key=lambda h: (h.priority, h.name))

    @classmethod
    def from_hook_configs(cls, configs: list[HookConfig], runner: LocalHookRunner) -> HookRegistry:
        registry = cls()
        for config in configs:
            fn = runner.wrap(config)
            registry.register(
                name=config.name,
                events=config.lifecycle_events,
                fn=fn,
                priority=config.priority,
                source=HookSource.LOCAL,
            )
        return registry
