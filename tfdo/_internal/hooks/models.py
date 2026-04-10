from __future__ import annotations

from enum import StrEnum
from typing import NotRequired, TypedDict

from pydantic import BaseModel, Field


class HookEnvVars(TypedDict):
    TFDO_COMMAND: str
    TFDO_HOOK_POINT: str
    TFDO_RUN_DIR: str
    TFDO_CMD_DIR: NotRequired[str]
    TFDO_RUN_STATE_DIR: NotRequired[str]
    TFDO_INVOKE_STATE_DIR: NotRequired[str]
    TFDO_ATTEMPT: NotRequired[str]


class HookInput(BaseModel):
    env_vars: HookEnvVars

    def env_dict(self) -> dict[str, str]:
        return dict(self.env_vars.items())  # pyright: ignore[reportReturnType]


class ExitEvent(BaseModel):
    reason: str


class InputModification(BaseModel):
    env_vars: dict[str, str] = Field(default_factory=dict)
    extra_var_files: list[str] = Field(default_factory=list)
    extra_args: list[str] = Field(default_factory=list)


class RetryEvent(BaseModel):
    reason: str


HookEffect = ExitEvent | InputModification | RetryEvent


class HookAbortError(Exception):
    def __init__(self, hook_name: str, exit_event: ExitEvent) -> None:
        self.hook_name = hook_name
        self.exit_event = exit_event
        super().__init__(f"hook '{hook_name}' requested exit: {exit_event.reason}")


class HookSource(StrEnum):
    INTERNAL = "internal"
    INSTALLED = "installed"
    LOCAL = "local"


DEFAULT_PRIORITY: dict[HookSource, int] = {
    HookSource.INTERNAL: 50,
    HookSource.INSTALLED: 500,
    HookSource.LOCAL: 5000,
}
