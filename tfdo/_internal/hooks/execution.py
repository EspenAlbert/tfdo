from __future__ import annotations

import logging
from contextvars import ContextVar
from pathlib import Path

from pydantic import BaseModel

from tfdo._internal.config.enums import LifecycleCommand, LifecycleEvent
from tfdo._internal.hooks.models import ExitEvent, HookEnvVars, HookInput
from tfdo._internal.hooks.registry import HookRegistry

logger = logging.getLogger(__name__)

_hook_env: ContextVar[dict[str, str]] = ContextVar("_hook_env", default={})

ENV_CMD_DIR = "TFDO_CMD_DIR"
ENV_RUN_STATE_DIR = "TFDO_RUN_STATE_DIR"
ENV_INVOKE_STATE_DIR = "TFDO_INVOKE_STATE_DIR"
ENV_RUN_DIR = "TFDO_RUN_DIR"
ENV_COMMAND = "TFDO_COMMAND"
ENV_HOOK_POINT = "TFDO_HOOK_POINT"
ENV_ATTEMPT = "TFDO_ATTEMPT"


def get_hook_env() -> dict[str, str]:
    return _hook_env.get()


def get_hook_env_var(key: str) -> str | None:
    return _hook_env.get().get(key)


class HookContext(BaseModel):
    run_dir: Path
    command: str
    cmd_dir: Path | None = None
    run_state_dir: Path | None = None
    invoke_state_dir: Path | None = None

    def to_hook_input(self, hook_point: LifecycleEvent) -> HookInput:
        env: HookEnvVars = {
            "TFDO_COMMAND": self.command,
            "TFDO_HOOK_POINT": hook_point,
            "TFDO_RUN_DIR": str(self.run_dir),
        }
        if self.cmd_dir is not None:
            env["TFDO_CMD_DIR"] = str(self.cmd_dir)
        if self.run_state_dir is not None:
            env["TFDO_RUN_STATE_DIR"] = str(self.run_state_dir)
        if self.invoke_state_dir is not None:
            env["TFDO_INVOKE_STATE_DIR"] = str(self.invoke_state_dir)
        return HookInput(env_vars=env)


def run_before_hooks(registry: HookRegistry, event: LifecycleEvent, ctx: HookContext) -> bool:
    hooks = registry.get_hooks(event)
    if not hooks:
        return True
    hook_input = ctx.to_hook_input(event)
    _hook_env.set(dict(hook_input.env_vars))
    for hook in hooks:
        try:
            effect = hook.fn(hook_input)
        except Exception:
            logger.exception(f"before hook '{hook.name}' raised an exception")
            return False
        if isinstance(effect, ExitEvent):
            logger.error(f"hook '{hook.name}' requested exit: {effect.reason}")
            return False
    return True


def run_after_hooks(registry: HookRegistry, event: LifecycleEvent, ctx: HookContext) -> None:
    hooks = registry.get_hooks(event)
    if not hooks:
        return
    hook_input = ctx.to_hook_input(event)
    _hook_env.set(dict(hook_input.env_vars))
    for hook in hooks:
        try:
            effect = hook.fn(hook_input)
        except Exception:
            logger.warning(f"after hook '{hook.name}' raised an exception, continuing", exc_info=True)
            continue
        if isinstance(effect, ExitEvent):
            logger.warning(f"after hook '{hook.name}' requested exit: {effect.reason}, ignoring in after phase")


_LIFECYCLE_EVENTS: dict[LifecycleCommand, tuple[LifecycleEvent, LifecycleEvent]] = {
    LifecycleCommand.INIT: (LifecycleEvent.INIT_BEFORE, LifecycleEvent.INIT_AFTER),
    LifecycleCommand.PLAN: (LifecycleEvent.PLAN_BEFORE, LifecycleEvent.PLAN_AFTER),
    LifecycleCommand.APPLY: (LifecycleEvent.APPLY_BEFORE, LifecycleEvent.APPLY_AFTER),
    LifecycleCommand.DESTROY: (LifecycleEvent.DESTROY_BEFORE, LifecycleEvent.DESTROY_AFTER),
}


def lifecycle_events(command: LifecycleCommand) -> tuple[LifecycleEvent, LifecycleEvent]:
    return _LIFECYCLE_EVENTS[command]
