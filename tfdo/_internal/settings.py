from pathlib import Path
from typing import ClassVar

from model_lib import StaticSettings
from pydantic import ConfigDict, Field

ENV_PREFIX = "TFDO_"


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

    log_level: str = Field(default="INFO", description="Log level for tfdo")
    passthrough: bool = Field(default=False, description="Disable parsed output, pass raw ANSI from terraform")
