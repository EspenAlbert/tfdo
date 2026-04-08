from enum import StrEnum


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


class BackendType(StrEnum):
    S3 = "s3"
    LOCAL = "local"


class TagsInject(StrEnum):
    ALWAYS = "always"
    NEVER = "never"
