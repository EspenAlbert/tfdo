from __future__ import annotations

import logging
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field
from zero_3rdparty.sections import CommentConfig, replace_sections

from tfdo._internal.config.config_model import TfDoConfig
from tfdo._internal.models import TfDoBaseInput

logger = logging.getLogger(__name__)

TOOL_NAME = "tfdo"
SECTION_ID = "ci-targets"
JUSTFILE_COMMENT_CONFIG = CommentConfig("#")
JUSTFILE_NAME = "justfile"

_VERBS = ("plan", "apply", "destroy", "init")


class SyncTargetGroup(StrEnum):
    PLAN = "plan"
    APPLY = "apply"
    DESTROY = "destroy"
    INIT = "init"


class SyncJustfileInput(TfDoBaseInput):
    config: TfDoConfig = Field(default_factory=TfDoConfig)
    selected_groups: list[SyncTargetGroup] = Field(default_factory=lambda: list(SyncTargetGroup))


class SyncJustfileResult(BaseModel):
    justfile_path: Path
    env_names: list[str]
    selected_groups: list[SyncTargetGroup]
    section_updated: bool


def _discover_env_names(config: TfDoConfig, work_dir: Path) -> list[str]:
    env_base = config.env_base_dir(work_dir)
    if not env_base.is_dir():
        return []
    return sorted(d.name for d in env_base.iterdir() if d.is_dir())


def _render_target(verb: str) -> str:
    lines: list[str] = [
        f"{verb}-env env:",
        f"    tfdo run --env {{{{env}}}} {verb}",
    ]
    return "\n".join(lines)


def _render_section(selected: list[SyncTargetGroup]) -> str:
    parts: list[str] = []
    for group in SyncTargetGroup:
        if group in selected:
            parts.append(_render_target(group))
    return "\n\n".join(parts)


def sync_justfile(input_model: SyncJustfileInput) -> SyncJustfileResult:
    work_dir = input_model.settings.work_dir
    justfile_path = work_dir / JUSTFILE_NAME

    env_names = _discover_env_names(input_model.config, work_dir)
    section_content = _render_section(input_model.selected_groups)

    existing = justfile_path.read_text() if justfile_path.is_file() else ""
    updated = replace_sections(
        dest_content=existing,
        src_sections={SECTION_ID: section_content},
        tool_name=TOOL_NAME,
        config=JUSTFILE_COMMENT_CONFIG,
    )

    section_updated = updated != existing
    if section_updated or not justfile_path.is_file():
        justfile_path.write_text(updated)

    return SyncJustfileResult(
        justfile_path=justfile_path,
        env_names=env_names,
        selected_groups=input_model.selected_groups,
        section_updated=section_updated,
    )
