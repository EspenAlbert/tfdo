from __future__ import annotations

import shutil
from pathlib import Path

from zero_3rdparty import file_utils

_TFDO_DIR = ".tfdo"
_PLAN_BIN = "plan.bin"
_PLAN_JSON = "plan.json"


def tfdo_dir(work_dir: Path) -> Path:
    return work_dir / _TFDO_DIR


def plan_bin_path(work_dir: Path) -> Path:
    return tfdo_dir(work_dir) / _PLAN_BIN


def plan_json_path(work_dir: Path) -> Path:
    return tfdo_dir(work_dir) / _PLAN_JSON


def resolve_plan_out(work_dir: Path, out: Path) -> Path:
    return out if out.is_absolute() else work_dir / out


def atomic_write_text(path: Path, content: str) -> None:
    # Write to a sibling .tmp then rename so plan.json is never half-written if we crash mid-write.
    tmp = path.with_suffix(path.suffix + ".tmp")
    file_utils.ensure_parents_write_text(tmp, content)
    tmp.replace(path)


def export_plan_bin(canonical: Path, user_out: Path) -> None:
    user_out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(canonical, user_out)
