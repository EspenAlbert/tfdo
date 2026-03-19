from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from ask_shell.console import interactive_shell
from model_lib import StaticSettings
from pydantic import ConfigDict, Field

ENV_PREFIX = "TFDO_"


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
