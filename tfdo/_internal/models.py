from pathlib import Path

from pydantic import BaseModel

from tfdo._internal.settings import TfDoSettings


class TfDoBaseInput(BaseModel):
    settings: TfDoSettings
    dry_run: bool = False


class InitInput(TfDoBaseInput):
    extra_args: list[str] = []


class PlanInput(TfDoBaseInput):
    out: Path | None = None
    json_output: bool = False
    var_file: Path | None = None
    init_first: bool = False


class ApplyInput(TfDoBaseInput):
    auto_approve: bool = False
    var_file: Path | None = None
    init_first: bool = False


class DestroyInput(TfDoBaseInput):
    auto_approve: bool = False
    var_file: Path | None = None
    init_first: bool = False


class CheckInput(TfDoBaseInput):
    fix: bool = False
    diff: bool = False
    init_first: bool = False


class InitResult(BaseModel):
    exit_code: int
    attempts_used: int
    cache_cleaned: bool = False
