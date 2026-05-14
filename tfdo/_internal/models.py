from __future__ import annotations

from enum import StrEnum
from functools import total_ordering
from pathlib import Path
from typing import ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tfdo._internal.check.models import CheckResult as RunDirProviderResult
from tfdo._internal.settings import TfDoSettings

_TF_PLUGIN_CACHE_DIR_KEY = "TF_PLUGIN_CACHE_DIR"


class InitMode(StrEnum):
    AUTO = "auto"
    ALWAYS = "always"
    NEVER = "never"


class TfDoBaseInput(BaseModel):
    settings: TfDoSettings
    dry_run: bool = False


class InitInput(TfDoBaseInput):
    backend_args: list[str] = Field(default_factory=list)
    extra_args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None

    @model_validator(mode="after")
    def _inject_plugin_cache(self) -> Self:
        env = dict(self.env or {})
        if _TF_PLUGIN_CACHE_DIR_KEY not in env:
            cache_dir = self.settings.cache_root / "tf_plugins"
            cache_dir.mkdir(parents=True, exist_ok=True)
            env[_TF_PLUGIN_CACHE_DIR_KEY] = str(cache_dir)
        self.env = env
        return self


class LifecycleInput(TfDoBaseInput):
    var_file: Path | None = None
    init_mode: InitMode = InitMode.AUTO
    extra_args: list[str] = Field(default_factory=list)
    init_backend_args: list[str] = Field(default_factory=list)


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
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    tflint: bool = False
    skip_check_providers: bool = False


class OutputInput(TfDoBaseInput):
    state: Path | None = None
    name: str | None = None


class OutputResult(BaseModel):
    exit_code: int
    outputs: dict[str, object] = Field(default_factory=dict)
    stderr: str | None = None


class InitResult(BaseModel):
    exit_code: int
    attempts_used: int
    stdout: str = ""
    stderr: str | None = None


class LifecycleResult(BaseModel):
    exit_code: int
    stdout: str = ""
    stderr: str | None = None


class PlanResult(LifecycleResult):
    pass


class ApplyResult(LifecycleResult):
    pass


class DestroyResult(LifecycleResult):
    pass


class TflintPos(BaseModel):
    line: int = 0
    column: int = 0


class TflintRange(BaseModel):
    filename: str = ""
    start: TflintPos = TflintPos()
    end: TflintPos = TflintPos()


class ValidateDiagnostic(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    severity: str = ""
    summary: str = ""
    detail: str = ""
    source_range: TflintRange | None = Field(default=None, validation_alias="range")

    @property
    def display(self) -> str:
        summary_s = self.summary.strip()
        detail_s = self.detail.strip()
        if summary_s and detail_s:
            body = f"{summary_s}: {detail_s}" if detail_s != summary_s else summary_s
        elif summary_s:
            body = summary_s
        elif detail_s:
            body = detail_s
        else:
            body = ""
        rng = self.source_range
        if rng and rng.filename:
            line = rng.start.line
            loc = f"{rng.filename}:{line}"
            if rng.start.column > 0:
                loc += f":{rng.start.column}"
            return f"{body} ({loc})" if body else loc
        return body


class ValidateOutput(BaseModel):
    valid: bool = True
    diagnostics: list[ValidateDiagnostic] = []

    ERROR_SEVERITY: ClassVar[str] = "error"

    @property
    def error_summaries(self) -> list[str]:
        return [d.display for d in self.diagnostics if d.severity == self.ERROR_SEVERITY and d.display]


class TflintRule(BaseModel):
    name: str = ""
    severity: str = ""
    link: str = ""


class TflintIssue(BaseModel):
    rule: TflintRule = TflintRule()
    message: str = ""
    range: TflintRange = TflintRange()
    callers: list[TflintRange] = []
    fixable: bool = False
    fixed: bool = False

    @property
    def display(self) -> str:
        r = self.range
        return f"[{self.rule.severity}] {self.rule.name}: {self.message} ({r.filename}:{r.start.line})"


class TflintError(BaseModel):
    summary: str = ""
    message: str = ""
    severity: str = ""
    range: TflintRange | None = None


class TflintOutput(BaseModel):
    issues: list[TflintIssue] = []
    errors: list[TflintError] = []


@total_ordering
class DirCheckResult(BaseModel):
    directory: Path
    fmt_files: list[str] = []
    validation_errors: list[str] = []
    tflint_issues: list[TflintIssue] = []
    missing_tfvars: list[str] = []
    provider_result: RunDirProviderResult | None = None
    skipped: bool = False
    backend_drift: bool = False

    @property
    def has_issues(self) -> bool:
        provider_fail = self.provider_result is not None and not self.provider_result.is_ok
        return (
            bool(self.fmt_files)
            or bool(self.validation_errors)
            or bool(self.tflint_issues)
            or bool(self.missing_tfvars)
            or provider_fail
            or self.backend_drift
        )

    def __lt__(self, other: Self) -> bool:
        if not isinstance(other, DirCheckResult):
            raise NotImplementedError
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
    def total_tflint_issues(self) -> list[TflintIssue]:
        return [i for d in self.dir_results for i in d.tflint_issues]

    @property
    def total_provider_failures(self) -> int:
        return sum(1 for d in self.dir_results if d.provider_result is not None and not d.provider_result.is_ok)

    @property
    def directories_checked(self) -> int:
        return sum(1 for d in self.dir_results if not d.skipped)

    @property
    def directories_skipped(self) -> list[Path]:
        return [d.directory for d in self.dir_results if d.skipped]
