from __future__ import annotations

from enum import StrEnum
from typing import TypedDict

from pydantic import BaseModel, Field


class _HookEnvVarsRequired(TypedDict):
    TFDO_COMMAND: str
    TFDO_HOOK_POINT: str
    TFDO_RUN_DIR: str


class HookEnvVars(_HookEnvVarsRequired, total=False):
    TFDO_CMD_DIR: str
    TFDO_RUN_STATE_DIR: str
    TFDO_INVOKE_STATE_DIR: str
    TFDO_ATTEMPT: str


class HookInput(BaseModel):
    env_vars: HookEnvVars


class ExitEvent(BaseModel):
    reason: str


class InputModification(BaseModel):
    env_vars: dict[str, str] = Field(default_factory=dict)
    extra_var_files: list[str] = Field(default_factory=list)
    extra_args: list[str] = Field(default_factory=list)


class RetryEvent(BaseModel):
    reason: str


HookEffect = ExitEvent | InputModification | RetryEvent


class HookSource(StrEnum):
    INTERNAL = "internal"
    INSTALLED = "installed"
    LOCAL = "local"


DEFAULT_PRIORITY: dict[HookSource, int] = {
    HookSource.INTERNAL: 50,
    HookSource.INSTALLED: 500,
    HookSource.LOCAL: 5000,
}
