from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from tfdo._internal.settings import TfDoSettings


class InitMode(StrEnum):
    AUTO = "auto"
    ALWAYS = "always"
    NEVER = "never"


class TfDoBaseInput(BaseModel):
    settings: TfDoSettings
    dry_run: bool = False


class InitInput(TfDoBaseInput):
    extra_args: list[str] = []


class LifecycleInput(TfDoBaseInput):
    var_file: Path | None = None
    init_mode: InitMode = InitMode.AUTO


class PlanInput(LifecycleInput):
    out: Path | None = None
    json_output: bool = False


class ApplyInput(LifecycleInput):
    auto_approve: bool = False


class DestroyInput(LifecycleInput):
    auto_approve: bool = False


class CheckInput(TfDoBaseInput):
    fix: bool = False
    diff: bool = False
    init_mode: InitMode = InitMode.AUTO


class InitResult(BaseModel):
    exit_code: int
    attempts_used: int


class LifecycleResult(BaseModel):
    exit_code: int


class PlanResult(LifecycleResult):
    pass


class ApplyResult(LifecycleResult):
    pass


class DestroyResult(LifecycleResult):
    pass
