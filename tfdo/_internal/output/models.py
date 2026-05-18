from __future__ import annotations

from enum import StrEnum
from functools import total_ordering

from pydantic import BaseModel, ConfigDict, Field


@total_ordering
class ResourceAction(StrEnum):
    NO_OP = "no-op"
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    REPLACE_DESTROY_FIRST = "delete+create"
    REPLACE_CREATE_FIRST = "create+delete"

    @classmethod
    def from_actions(cls, actions: list[str]) -> ResourceAction:
        key = "+".join(actions)
        match key:
            case "no-op":
                return cls.NO_OP
            case "create":
                return cls.CREATE
            case "read":
                return cls.READ
            case "update":
                return cls.UPDATE
            case "delete":
                return cls.DELETE
            case "delete+create":
                return cls.REPLACE_DESTROY_FIRST
            case "create+delete":
                return cls.REPLACE_CREATE_FIRST
            case _:
                raise ValueError(f"unknown resource actions: {actions!r}")

    def __lt__(self, other: object) -> bool:
        match other:
            case ResourceAction():
                self_rank = _PLAN_ACTION_RANK[self]
                other_rank = _PLAN_ACTION_RANK[other]
                if self_rank != other_rank:
                    return self_rank < other_rank
                return self.value < other.value
            case _:
                return NotImplemented


_PLAN_ACTION_RANK: dict[ResourceAction, int] = {
    ResourceAction.DELETE: 0,
    ResourceAction.REPLACE_DESTROY_FIRST: 1,
    ResourceAction.REPLACE_CREATE_FIRST: 1,
    ResourceAction.UPDATE: 2,
    ResourceAction.CREATE: 3,
    ResourceAction.READ: 4,
    ResourceAction.NO_OP: 5,
}


class Change(BaseModel):
    model_config = ConfigDict(extra="ignore")

    actions: list[str]
    before: dict[str, object] | None = None
    after: dict[str, object] | None = None
    after_unknown: dict[str, object] | bool = False
    before_sensitive: dict[str, object] | bool = False
    after_sensitive: dict[str, object] | bool = False
    replace_paths: list[list[str | int]] | None = None
    importing: dict[str, object] | None = None

    def action(self) -> ResourceAction:
        return ResourceAction.from_actions(self.actions)


class ResourceChange(BaseModel):
    model_config = ConfigDict(extra="ignore")

    address: str
    mode: str
    type: str
    name: str
    change: Change
    module_address: str | None = None
    index: int | str | None = None
    provider_name: str | None = None
    action_reason: str | None = None


class OutputChange(BaseModel):
    model_config = ConfigDict(extra="ignore")

    actions: list[str]
    before: object | None = None
    after: object | None = None
    after_unknown: bool = False
    before_sensitive: bool = False
    after_sensitive: bool = False


class PlanOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    format_version: str
    terraform_version: str | None = None
    errored: bool
    applyable: bool | None = None
    complete: bool | None = None
    resource_changes: list[ResourceChange] = Field(default_factory=list)
    resource_drift: list[ResourceChange] = Field(default_factory=list)
    output_changes: dict[str, OutputChange] = Field(default_factory=dict)
