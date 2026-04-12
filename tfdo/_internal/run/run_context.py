from __future__ import annotations

from pydantic import BaseModel, Field


class RunDirContext(BaseModel):
    name: str
    path: str
    repo_owner: str
    repo_name: str
    tags: dict[str, str] = Field(default_factory=dict)
