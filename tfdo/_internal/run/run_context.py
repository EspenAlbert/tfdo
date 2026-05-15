from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from tfdo._internal.config.config_model import TfDoConfig


class RunDirContext(BaseModel):
    name: str
    path: str
    repo_owner: str
    repo_name: str
    tags: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_config(cls, relative_path: str, config: TfDoConfig) -> RunDirContext:
        ci = config.ci
        return cls(
            name=relative_path.rsplit("/", 1)[-1],
            path=relative_path,
            repo_owner=ci.repo_org or "" if ci else "",
            repo_name=ci.repo_name or "" if ci else "",
            tags=config.tags,
        )
