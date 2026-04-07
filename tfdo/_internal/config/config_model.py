from __future__ import annotations

from typing import Self

from pydantic import BaseModel, Field, model_validator

from tfdo._internal.config.enums import BackendType, LifecycleEvent
from tfdo._internal.settings import CheckConfig


class BackendDefaults(BaseModel):
    type: BackendType = BackendType.S3
    bucket: str | None = None
    key: str | None = None
    region: str | None = None
    dynamodb_table: str | None = None
    encrypt: bool = True
    path: str | None = None

    @model_validator(mode="after")
    def _validate_required_fields(self) -> Self:
        if self.type == BackendType.S3 and (not self.bucket or not self.key):
            raise ValueError("backend type=s3 requires 'bucket' and 'key'")
        if self.type == BackendType.LOCAL and not self.path:
            raise ValueError("backend type=local requires 'path'")
        return self


class HookConfig(BaseModel):
    name: str
    cmd: str | None = None
    py_locate: str | None = None
    lifecycle_events: list[LifecycleEvent]
    timeout_seconds: int = 30
    priority: int = 5000

    @model_validator(mode="after")
    def _exactly_one_executor(self) -> Self:
        has_cmd = self.cmd is not None
        has_py = self.py_locate is not None
        if has_cmd == has_py:
            raise ValueError("exactly one of 'cmd' or 'py_locate' must be set")
        return self


class DependencyRef(BaseModel):
    ref: str
    outputs: bool = True


class TfDoConfig(BaseModel):
    binary: str | None = None
    tf_version: str | None = None
    backend: BackendDefaults | None = None
    check: CheckConfig | None = None
    tags_inject: bool | None = None

    tags: dict[str, str] = Field(default_factory=dict)
    hook_configs: list[HookConfig] = Field(default_factory=list)

    dependencies: list[DependencyRef] = Field(default_factory=list)
    var_files: list[str] = Field(default_factory=list)

    run_dir_discovery: str | None = None
