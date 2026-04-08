from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator

from tfdo._internal.config.enums import BackendType, LifecycleEvent
from tfdo._internal.settings import CheckConfig


def _backend_config_flag(key: str, value: str) -> str:
    return f"-backend-config={key}={value}"


class S3Backend(BaseModel):
    type: Literal[BackendType.S3] = BackendType.S3
    bucket: str
    key: str
    region: str | None = None
    dynamodb_table: str | None = None
    encrypt: bool | None = None

    @property
    def config_flags(self) -> list[str]:
        flags = [
            _backend_config_flag("bucket", self.bucket),
            _backend_config_flag("key", self.key),
        ]
        if self.region:
            flags.append(_backend_config_flag("region", self.region))
        if self.dynamodb_table:
            flags.append(_backend_config_flag("dynamodb_table", self.dynamodb_table))
        if self.encrypt is not None:
            flags.append(_backend_config_flag("encrypt", str(self.encrypt).lower()))
        return flags


class LocalBackend(BaseModel):
    type: Literal[BackendType.LOCAL] = BackendType.LOCAL
    path: str

    @property
    def config_flags(self) -> list[str]:
        return [_backend_config_flag("path", self.path)]


BackendConfig = S3Backend | LocalBackend


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
    backend: Annotated[BackendConfig, Field(discriminator="type")] | None = None
    check: CheckConfig | None = None
    tags_inject: bool | None = None

    tags: dict[str, str] = Field(default_factory=dict)
    hook_configs: list[HookConfig] = Field(default_factory=list)

    dependencies: list[DependencyRef] = Field(default_factory=list)
    var_files: list[str] = Field(default_factory=list)

    run_dir_discovery: str | None = None
