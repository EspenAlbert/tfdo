from __future__ import annotations

import logging
from enum import StrEnum
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


class InteractiveMode(StrEnum):
    AUTO = "auto"
    ALWAYS = "always"
    NEVER = "never"


class TfDoSettings(StaticSettings):
    model_config = ConfigDict(populate_by_name=True)  # type: ignore

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


class CheckConfig(BaseModel):
    tflint: bool = False


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


def resolve_tflint_flag(cli_value: bool | None, settings: TfDoSettings) -> bool:
    if cli_value is not None:
        return cli_value
    user_config = load_user_config(settings)
    if user_config.check and user_config.check.tflint:
        return True
    return False
