from __future__ import annotations

from enum import StrEnum


class HookOnError(StrEnum):
    ABORT = "abort"
    WARN = "warn"


class LifecycleEvent(StrEnum):
    INIT_BEFORE = "init_before"
    INIT_AFTER = "init_after"
    PLAN_BEFORE = "plan_before"
    PLAN_AFTER = "plan_after"
    APPLY_BEFORE = "apply_before"
    APPLY_AFTER = "apply_after"
    DESTROY_BEFORE = "destroy_before"
    DESTROY_AFTER = "destroy_after"
    ON_OK = "on_ok"
    ON_ERROR = "on_error"
    ON_ALL_DONE = "on_all_done"

    @classmethod
    def default_on_error(cls, event: LifecycleEvent) -> HookOnError:
        return HookOnError.ABORT if event.endswith("_before") else HookOnError.WARN


class BackendType(StrEnum):
    S3 = "s3"
    LOCAL = "local"


class LifecycleCommand(StrEnum):
    PLAN = "plan"
    APPLY = "apply"
    DESTROY = "destroy"
    INIT = "init"


class TagsInject(StrEnum):
    ALWAYS = "always"
    NEVER = "never"


class EnvVarLoadMode(StrEnum):
    auto = "auto"
    load = "load"
    skip = "skip"
