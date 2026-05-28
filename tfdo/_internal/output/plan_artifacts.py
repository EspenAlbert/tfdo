from __future__ import annotations

import re
import shutil
from pathlib import Path

from zero_3rdparty import file_utils

_TFDO_DIR = ".tfdo"
_PLAN_BIN = "plan.bin"
_PLAN_JSON = "plan.json"
_DEBUG_LOG = "debug.log"
_DEBUG_OLD_DIR = "debug_old"
_DEBUG_OLD_PATTERN = r"^(?P<num>\d{2})_debug\.log$"


def tfdo_dir(work_dir: Path) -> Path:
    return work_dir / _TFDO_DIR


def plan_bin_path(work_dir: Path) -> Path:
    return tfdo_dir(work_dir) / _PLAN_BIN


def plan_json_path(work_dir: Path) -> Path:
    return tfdo_dir(work_dir) / _PLAN_JSON


def debug_log_path(work_dir: Path) -> Path:
    return tfdo_dir(work_dir) / _DEBUG_LOG


def _next_debug_old_name(old_dir: Path) -> str:
    highest = 0
    for path in old_dir.iterdir():
        if match := re.match(_DEBUG_OLD_PATTERN, path.name):
            highest = max(highest, int(match.group("num")))
    return f"{highest + 1:02d}_debug.log"


def begin_lifecycle_debug_log(work_dir: Path) -> None:
    current = debug_log_path(work_dir)
    if not current.is_file():
        return
    old_dir = tfdo_dir(work_dir) / _DEBUG_OLD_DIR
    old_dir.mkdir(parents=True, exist_ok=True)
    current.rename(old_dir / _next_debug_old_name(old_dir))


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
