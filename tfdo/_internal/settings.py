from __future__ import annotations

import logging
from enum import StrEnum
from importlib.resources import files as _importlib_files
from pathlib import Path
from typing import ClassVar

import platformdirs
import yaml
from ask_shell.console import interactive_shell
from model_lib import StaticSettings
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

ENV_PREFIX = "TFDO_"
USER_CONFIG_FILENAME = "config.yaml"
SCHEMA_CACHE_SUBDIR = "schemas"
BACKENDS_SUBDIR = "backends"
ENV_VARS_SUBDIR = "env_vars"


class InteractiveMode(StrEnum):
    AUTO = "auto"
    ALWAYS = "always"
    NEVER = "never"


class TfDoSettings(StaticSettings):
    model_config = ConfigDict(populate_by_name=True)  # type: ignore

    DEP_TFVARS_SUFFIX: ClassVar[str] = ".dep.tfvars.json"

    ENV_NAME_BINARY: ClassVar[str] = f"{ENV_PREFIX}BINARY"
    binary: str = Field(
        default="terraform",
        alias=ENV_NAME_BINARY,
        description="Terraform binary name or path (terraform, tofu, etc.)",
    )

    ENV_NAME_TF_VERSION: ClassVar[str] = f"{ENV_PREFIX}TF_VERSION"
    tf_version: str | None = Field(
        default=None,
        alias=ENV_NAME_TF_VERSION,
        description="When set, binary becomes 'mise x terraform@{version} -- {binary}'",
    )

    ENV_NAME_WORK_DIR: ClassVar[str] = f"{ENV_PREFIX}WORK_DIR"
    work_dir: Path = Field(
        default_factory=Path.cwd,
        alias=ENV_NAME_WORK_DIR,
        description="Working directory for terraform commands",
    )

    ENV_NAME_INTERACTIVE: ClassVar[str] = f"{ENV_PREFIX}INTERACTIVE"
    interactive: InteractiveMode = Field(
        default=InteractiveMode.AUTO,
        alias=f"{ENV_PREFIX}INTERACTIVE",
        description="Interactive mode: auto (detect TTY), always (force stdin), never (no stdin, require --auto-approve)",
    )

    log_level: str = Field(default="INFO", description="Log level for tfdo")
    passthrough: bool = Field(default=False, description="Disable parsed output, pass raw ANSI from terraform")

    ENV_NAME_VERBOSE_SHELL: ClassVar[str] = f"{ENV_PREFIX}VERBOSE_SHELL"
    verbose_shell: bool = Field(
        default=False,
        alias=ENV_NAME_VERBOSE_SHELL,
        description="Log every successful shell command completion (default is errors only for tfdo)",
    )

    ENV_NAME_BACKENDS_DIRS: ClassVar[str] = f"{ENV_PREFIX}BACKENDS_DIRS"
    backends_dirs_raw: str | None = Field(default=None, alias=ENV_NAME_BACKENDS_DIRS)

    ENV_NAME_PROVIDER_HINTS_PATH: ClassVar[str] = f"{ENV_PREFIX}PROVIDER_HINTS_PATH"
    provider_hints_path: Path | None = Field(default=None, alias=ENV_NAME_PROVIDER_HINTS_PATH)

    ENV_NAME_ENV_VARS_DIRS: ClassVar[str] = f"{ENV_PREFIX}ENV_VARS_DIRS"
    env_vars_dirs_raw: str | None = Field(default=None, alias=ENV_NAME_ENV_VARS_DIRS)

    @property
    def backends_dirs(self) -> list[Path]:
        if self.backends_dirs_raw:
            return [Path(p.strip()) for p in self.backends_dirs_raw.split(":") if p.strip()]
        return [self.static_root / BACKENDS_SUBDIR]

    @property
    def resolved_provider_hints_path(self) -> Path:
        if self.provider_hints_path is not None:
            return self.provider_hints_path
        return Path(str(_importlib_files("tfdo._internal.config").joinpath("provider_hints.yaml")))

    @property
    def env_vars_dirs(self) -> list[Path]:
        if not self.env_vars_dirs_raw:
            return []
        return [Path(p.strip()) for p in self.env_vars_dirs_raw.split(":") if p.strip()]

    def resolve_env_vars_dirs(self) -> list[Path]:
        if self.env_vars_dirs:
            return self.env_vars_dirs
        return [self.static_root / ENV_VARS_SUBDIR]

    @property
    def is_interactive(self) -> bool:
        if self.interactive == InteractiveMode.ALWAYS:
            return True
        if self.interactive == InteractiveMode.NEVER:
            return False
        return interactive_shell()

    @property
    def user_config_path(self) -> Path:
        return Path(platformdirs.user_config_dir(self.app_name())) / USER_CONFIG_FILENAME

    @property
    def schema_cache_dir(self) -> Path:
        return Path(platformdirs.user_cache_dir(self.app_name())) / SCHEMA_CACHE_SUBDIR

    def with_work_dir(self, path: Path) -> TfDoSettings:
        return self.model_copy(update={"work_dir": path})

    def with_overrides(self, work_dir: Path, binary: str | None = None, tf_version: str | None = None) -> TfDoSettings:
        updates: dict = {"work_dir": work_dir}
        if binary:
            updates["binary"] = binary
        if tf_version:
            updates["tf_version"] = tf_version
        return self.model_copy(update=updates)


class CheckConfig(BaseModel):
    tflint: bool = False
    skip_check_providers: bool = False


class TfDoUserConfig(BaseModel):
    check: CheckConfig | None = None


def load_user_config(settings: TfDoSettings) -> TfDoUserConfig:
    path = settings.user_config_path
    if not path.is_file():
        return TfDoUserConfig()
    try:
        data = yaml.safe_load(path.read_text()) or {}
        return TfDoUserConfig(**data)
    except Exception:
        logger.warning(f"failed to parse user config at {path}")
        return TfDoUserConfig()
