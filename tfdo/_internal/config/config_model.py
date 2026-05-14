from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator

from tfdo._internal.config.discovery_pattern import (
    DiscoveryPattern,
    iter_dirs_at_depth,
    parse_discovery_pattern,
)
from tfdo._internal.config.enums import BackendType, HookOnError, LifecycleEvent, TagsInject
from tfdo._internal.settings import CheckConfig

DEFAULT_DISCOVERY_PATTERN = "envs/{env}/{run_dir}"
ENV_SELECTOR_NAME = "env"


def _backend_config_flag(key: str, value: str) -> str:
    return f"-backend-config={key}={value}"


class S3Backend(BaseModel):
    type: Literal[BackendType.S3] = BackendType.S3
    bucket: str
    key: str
    region: str | None = None
    dynamodb_table: str | None = None
    encrypt: bool | None = None
    use_lockfile: bool | None = None

    @model_validator(mode="after")
    def _default_use_lockfile(self) -> Self:
        self.use_lockfile = self.use_lockfile or (self.dynamodb_table is None)
        return self

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
        if self.use_lockfile is True:
            flags.append(_backend_config_flag("use_lockfile", "true"))
        return flags

    @property
    def hcl_config(self) -> dict[str, object]:
        config: dict[str, object] = {
            "bucket": f'"{self.bucket}"',
            "key": f'"{self.key}"',
        }
        if self.region:
            config["region"] = f'"{self.region}"'
        if self.encrypt is not None:
            config["encrypt"] = self.encrypt
        if self.use_lockfile is True:
            config["use_lockfile"] = self.use_lockfile
        return config


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
    on_error: HookOnError | None = None

    @model_validator(mode="after")
    def _exactly_one_executor(self) -> Self:
        has_cmd = self.cmd is not None
        has_py = self.py_locate is not None
        if has_cmd == has_py:
            raise ValueError("exactly one of 'cmd' or 'py_locate' must be set")
        return self


class DependencyRef(BaseModel):
    ref: str
    outputs: dict[str, str] = Field(default_factory=dict)
    outputs_mock: dict[str, str] = Field(default_factory=dict)


_LOCAL_SOURCE_PREFIXES = ("./", "../", "/")


class ProviderConstraint(BaseModel):
    name: str
    constraint: str | None = None


class ModuleConstraint(BaseModel):
    source: str
    constraint: str | None = None

    @model_validator(mode="after")
    def _reject_local_source(self) -> Self:
        if any(self.source.startswith(p) for p in _LOCAL_SOURCE_PREFIXES):
            raise ValueError(f"local module source not allowed in tfdo.yaml: {self.source!r}")
        return self


TFDO_DEFAULT_INSTALL = "git+https://github.com/EspenAlbert/tfdo.git@main"


class CiConfig(BaseModel):
    oidc: bool = False
    repo_org: str | None = None
    repo_name: str | None = None
    oidc_roles: dict[str, str] = Field(default_factory=dict)
    tfdo_install: str = TFDO_DEFAULT_INSTALL


class TfDoConfig(BaseModel):
    binary: str | None = None
    tf_version: str | None = None
    backend: Annotated[BackendConfig, Field(discriminator="type")] | None = None
    check: CheckConfig | None = None
    tags_inject: TagsInject | None = None

    tags: dict[str, str] = Field(default_factory=dict)
    hook_configs: list[HookConfig] = Field(default_factory=list)

    dependencies: list[DependencyRef] = Field(default_factory=list)
    var_files: list[str] = Field(default_factory=list)

    run_dir_discovery: str = DEFAULT_DISCOVERY_PATTERN
    providers: list[ProviderConstraint] = Field(default_factory=list)
    modules: list[ModuleConstraint] = Field(default_factory=list)
    env_var_files: list[str] = Field(default_factory=list)
    ci: CiConfig | None = None

    @model_validator(mode="after")
    def _validate_discovery_pattern(self) -> Self:
        pattern = parse_discovery_pattern(self.run_dir_discovery)
        names = pattern.selector_names
        if not names or names[0] != ENV_SELECTOR_NAME:
            raise ValueError(
                f"run_dir_discovery must have '{{{ENV_SELECTOR_NAME}}}' as the first selector, "
                f"got: {self.run_dir_discovery!r}"
            )
        return self

    def parsed_pattern(self) -> DiscoveryPattern:
        return parse_discovery_pattern(self.run_dir_discovery)

    @property
    def selector_names(self) -> list[str]:
        return self.parsed_pattern().selector_names

    def run_dir_relative(self, env_name: str, run_dir_name: str) -> str:
        selectors = self.selector_names
        result = self.run_dir_discovery
        # First placeholder → env, last placeholder → run-dir name
        if selectors:
            result = result.replace(f"{{{selectors[0]}}}", env_name)
        if len(selectors) >= 2:
            result = result.replace(f"{{{selectors[-1]}}}", run_dir_name)
        return result

    @property
    def env_path_prefix(self) -> str:
        """Literal directory prefix before the first placeholder (e.g. 'envs')."""
        return self.run_dir_discovery.strip("/").split("{")[0].rstrip("/")

    def env_base_dir(self, work_dir: Path) -> Path:
        return work_dir / self.env_path_prefix if self.env_path_prefix else work_dir

    def _matched_dirs(self, work_dir: Path) -> list[tuple[Path, dict[str, str]]]:
        """Walk work_dir for directories matching the discovery pattern."""
        pattern = self.parsed_pattern()
        total_segments = len(self.run_dir_discovery.strip("/").split("/"))
        optional_count = len(pattern.optional_selectors)
        results: list[tuple[Path, dict[str, str]]] = []
        for directory in iter_dirs_at_depth(work_dir, total_segments - optional_count, total_segments):
            rel = str(directory.relative_to(work_dir))
            if (selectors := pattern.match(rel)) is not None:
                results.append((directory, selectors))
        return results

    def envs(self, work_dir: Path) -> list[Path]:
        base = self.env_base_dir(work_dir)
        return sorted(d for d in base.iterdir() if d.is_dir()) if base.is_dir() else []

    def run_dirs(self, work_dir: Path, env_name: str | None = None) -> list[Path]:
        names = self.selector_names
        if not names:
            return []
        first_sel = names[0]
        if len(names) < 2:
            if env_name:
                return [p for p, sel in self._matched_dirs(work_dir) if sel.get(first_sel) == env_name]
            return [p for p, _ in self._matched_dirs(work_dir)]
        if env_name is not None:
            return sorted(p for p, sel in self._matched_dirs(work_dir) if sel.get(first_sel) == env_name)
        return sorted(p for p, _ in self._matched_dirs(work_dir))


def merge_providers(parents: list[TfDoConfig], child: TfDoConfig) -> list[ProviderConstraint]:
    """Merge provider constraints from root → env → run-dir; child wins for constraint."""
    merged: dict[str, ProviderConstraint] = {}
    for cfg in [*parents, child]:
        for p in cfg.providers:
            merged[p.name] = p
    return list(merged.values())


def merge_modules(parents: list[TfDoConfig], child: TfDoConfig) -> list[ModuleConstraint]:
    merged: dict[str, ModuleConstraint] = {}
    for cfg in [*parents, child]:
        for m in cfg.modules:
            merged[m.source] = m
    return list(merged.values())


def merge_env_var_files(parents: list[TfDoConfig], child: TfDoConfig) -> list[str]:
    """Concatenate env_var_files from root → env → run-dir; later entries win on key collision when loaded."""
    result: list[str] = []
    for cfg in [*parents, child]:
        result.extend(cfg.env_var_files)
    return result
