from __future__ import annotations

import inspect
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from pydantic import BaseModel

from tfdo._internal.config.enums import HookOnError, LifecycleEvent
from tfdo._internal.hooks.models import HookEffect, HookInput, HookSource

if TYPE_CHECKING:
    from tfdo._internal.config.config_model import HookConfig
    from tfdo._internal.hooks.runner import LocalHookRunner

logger = logging.getLogger(__name__)


HookFn = Callable[[HookInput], HookEffect | None]
HookFnAny = HookFn | Callable[[], HookEffect | None]


def _wrap_zero_arg(fn: HookFnAny) -> HookFn:
    def _wrapped(_input: HookInput) -> HookEffect | None:
        return fn()  # pyright: ignore[reportCallIssue]

    return _wrapped


class RegisteredHook(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    name: str
    source: HookSource
    priority: int
    on_error: HookOnError
    fn: HookFn


@dataclass
class HookRegistry:
    _hooks: dict[LifecycleEvent, list[RegisteredHook]] = field(init=False, default_factory=lambda: defaultdict(list))

    def register(
        self,
        name: str,
        events: list[LifecycleEvent],
        fn: HookFnAny,
        priority: int,
        source: HookSource,
        on_error: HookOnError | None = None,
    ) -> None:
        params = inspect.signature(fn).parameters
        wrapped: HookFn = _wrap_zero_arg(fn) if not params else fn  # pyright: ignore[reportAssignmentType]
        for event in events:
            mode = on_error or LifecycleEvent.default_on_error(event)
            hook = RegisteredHook(name=name, source=source, priority=priority, on_error=mode, fn=wrapped)
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
                on_error=config.on_error,
            )
        return registry
