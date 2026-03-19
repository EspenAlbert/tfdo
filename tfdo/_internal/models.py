from __future__ import annotations

from enum import StrEnum
from functools import total_ordering
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
    include_patterns: list[str] = []
    exclude_patterns: list[str] = []


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


class ValidateDiagnostic(BaseModel):
    severity: str = ""
    summary: str = ""


class ValidateOutput(BaseModel):
    valid: bool = True
    diagnostics: list[ValidateDiagnostic] = []

    @property
    def error_summaries(self) -> list[str]:
        return [d.summary for d in self.diagnostics if d.summary]


@total_ordering
class DirCheckResult(BaseModel):
    directory: Path
    fmt_files: list[str] = []
    validation_errors: list[str] = []
    skipped: bool = False

    @property
    def has_issues(self) -> bool:
        return bool(self.fmt_files) or bool(self.validation_errors)

    def __lt__(self, other: Self) -> bool:
        if not isinstance(other, DirCheckResult):
            return NotImplemented
        return self.directory < other.directory


class CheckResult(BaseModel):
    exit_code: int
    dir_results: list[DirCheckResult] = []

    @model_validator(mode="after")
    def _sort_dir_results(self) -> Self:
        self.dir_results.sort()
        return self

    @property
    def total_fmt_files(self) -> list[str]:
        return [f for d in self.dir_results for f in d.fmt_files]

    @property
    def total_validation_errors(self) -> list[str]:
        return [e for d in self.dir_results for e in d.validation_errors]

    @property
    def directories_checked(self) -> int:
        return sum(1 for d in self.dir_results if not d.skipped)

    @property
    def directories_skipped(self) -> list[Path]:
        return [d.directory for d in self.dir_results if d.skipped]
