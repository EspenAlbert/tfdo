from __future__ import annotations

import os
from pathlib import Path

from tfdo._internal.output import plan_artifacts


def resolved_debug_log_path(work_dir: Path) -> Path:
    if path := os.environ.get("TF_LOG_PATH"):
        return Path(path).expanduser().resolve()
    return plan_artifacts.debug_log_path(work_dir).resolve()


def lifecycle_env(work_dir: Path) -> dict[str, str]:
    plan_artifacts.tfdo_dir(work_dir).mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.setdefault("TF_LOG", "DEBUG")
    env.setdefault("TF_LOG_PATH", str(resolved_debug_log_path(work_dir)))
    return env
