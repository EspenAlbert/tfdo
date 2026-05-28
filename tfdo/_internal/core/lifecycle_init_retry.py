from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from tfdo._internal.core import lifecycle_env, terraform_init
from tfdo._internal.models import InitInput, InitMode, LifecycleInput, LifecycleResult

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=LifecycleResult)

INIT_NEEDED_PATTERNS: list[str] = [
    "terraform init",
    "provider not installed",
    "Missing required provider",
    "Backend initialization required",
    "Module not installed",
]

BACKEND_CHANGED_PATTERNS: list[str] = [
    "Backend configuration changed",
]


def is_backend_changed(stderr: str) -> bool:
    lower = stderr.lower()
    return any(p.lower() in lower for p in BACKEND_CHANGED_PATTERNS)


def needs_init(stderr: str) -> bool:
    lower = stderr.lower()
    return any(p.lower() in lower for p in INIT_NEEDED_PATTERNS)


def run_with_init_retry(
    input_model: LifecycleInput,
    subcommand: str,
    result_cls: type[T],
    run_once: Callable[[], T],
) -> T:
    settings = input_model.settings
    mode = input_model.init_mode
    force_init = mode == InitMode.ALWAYS
    init_env = lifecycle_env.lifecycle_env(settings.work_dir)

    if force_init:
        init_result = terraform_init.init(
            InitInput(
                settings=settings,
                backend_args=input_model.init_backend_args,
                env=init_env,
            )
        )
        if init_result.exit_code != 0:
            return result_cls(exit_code=init_result.exit_code, stderr=init_result.stderr)

    result = run_once()
    stderr = result.stderr or ""
    if result.exit_code != 0 and mode != InitMode.NEVER and not force_init:
        if is_backend_changed(stderr):
            logger.warning(
                f"backend configuration changed in {settings.work_dir}. "
                "Run 'tfdo check --fix' to update backend.tf, then 'terraform init -reconfigure' to accept "
                "the new backend, or 'terraform init -migrate-state' to migrate existing state."
            )
        elif needs_init(stderr):
            logger.info(f"auto-init: detected init-needed error, running terraform init before retrying {subcommand}")
            init_result = terraform_init.init(
                InitInput(
                    settings=settings,
                    backend_args=input_model.init_backend_args,
                    env=init_env,
                )
            )
            if init_result.exit_code != 0:
                return result_cls(exit_code=init_result.exit_code, stderr=init_result.stderr)
            result = run_once()
    return result


def init_input_for_output_retry(stderr: str, base: InitInput) -> InitInput | None:
    if is_backend_changed(stderr):
        return base.model_copy(update={"extra_args": [*base.extra_args, "-reconfigure"]})
    if needs_init(stderr):
        return base
    return None
