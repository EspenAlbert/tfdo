from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, model_validator

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


def _check_interactive_approval(subcommand: str, auto_approve: bool, settings: TfDoSettings) -> None:
    if auto_approve or settings.is_interactive:
        return
    raise ValueError(
        f"terraform {subcommand} requires approval but no interactive terminal is available. "
        f"Run with --auto-approve or set {TfDoSettings.ENV_NAME_INTERACTIVE}=always (--interactive always) to force interactive mode."
    )


class ApplyInput(LifecycleInput):
    auto_approve: bool = False

    @model_validator(mode="after")
    def _require_approval_source(self) -> Self:
        _check_interactive_approval("apply", self.auto_approve, self.settings)
        return self


class DestroyInput(LifecycleInput):
    auto_approve: bool = False

    @model_validator(mode="after")
    def _require_approval_source(self) -> Self:
        _check_interactive_approval("destroy", self.auto_approve, self.settings)
        return self


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


class CheckResult(BaseModel):
    exit_code: int
    fmt_issues: int = 0
    validation_errors: list[str] = []
    directories_checked: int = 0
    directories_skipped: int = 0
