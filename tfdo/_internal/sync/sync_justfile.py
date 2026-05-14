from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, Field
from zero_3rdparty.sections import CommentConfig, replace_sections

from tfdo._internal.config.config_model import ENV_SELECTOR_NAME, TfDoConfig
from tfdo._internal.models import TfDoBaseInput

logger = logging.getLogger(__name__)

TOOL_NAME = "tfdo"
SECTION_ID = "ci-targets"
JUSTFILE_COMMENT_CONFIG = CommentConfig("#")
JUSTFILE_NAME = "justfile"


class SyncJustfileInput(TfDoBaseInput):
    config: TfDoConfig = Field(default_factory=TfDoConfig)


class SyncJustfileResult(BaseModel):
    justfile_path: Path
    target_names: list[str]
    section_updated: bool


def _selector_flag(name: str, value: str) -> str:
    if name == "env":
        return f"--env {value}"
    return f"--app {value}"


def _render_target(target_name: str, selectors: dict[str, str]) -> str:
    flags = " ".join(_selector_flag(k, v) for k, v in selectors.items())
    return f'{target_name} cmd *args:\n    tfdo run {flags} {{{{cmd}}}} "$@"'


def _discover_targets(config: TfDoConfig, work_dir: Path) -> list[tuple[str, dict[str, str]]]:
    """Return (target_name, selectors) pairs from env/run-dir directory layout."""
    selector_names = config.selector_names
    run_dir_selector = selector_names[1] if len(selector_names) >= 2 else None

    targets: list[tuple[str, dict[str, str]]] = []
    for env_path in config.envs(work_dir):
        env_name = env_path.name
        if run_dir_selector is not None:
            run_dir_paths = config.run_dirs(work_dir, env_name)
            if run_dir_paths:
                for rd_path in run_dir_paths:
                    target_name = f"{env_name}-{rd_path.name}"
                    selectors = {ENV_SELECTOR_NAME: env_name, run_dir_selector: rd_path.name}
                    targets.append((target_name, selectors))
                continue
        targets.append((env_name, {ENV_SELECTOR_NAME: env_name}))
    return targets


def _render_section(targets: list[tuple[str, dict[str, str]]]) -> str:
    return "\n\n".join(_render_target(name, selectors) for name, selectors in targets)


def sync_justfile(input_model: SyncJustfileInput) -> SyncJustfileResult:
    work_dir = input_model.settings.work_dir
    justfile_path = work_dir / JUSTFILE_NAME

    targets = _discover_targets(input_model.config, work_dir)
    section_content = _render_section(targets)

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
        target_names=[name for name, _ in targets],
        section_updated=section_updated,
    )
