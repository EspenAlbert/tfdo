from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from zero_3rdparty.file_utils import ensure_parents_write_text

from tfdo._internal.config.config_model import TfDoConfig
from tfdo._internal.hcl_roundtrip import HclValue, update_module_block, update_resource_block
from tfdo._internal.hcl_run_dir_gen import _hcl_value_to_raw, terraform_fmt
from tfdo._internal.models import TfDoBaseInput
from tfdo._internal.run.discovery import DiscoveryPattern, discover_run_dirs, parse_discovery_pattern

logger = logging.getLogger(__name__)


class SrcEnvNotFoundError(ValueError): ...


class DstEnvExistsError(ValueError): ...


class ModuleCallEdit(BaseModel):
    run_dir: str
    module_name: str
    attrs: dict[str, HclValue] = Field(default_factory=dict)


class ResourceEdit(BaseModel):
    run_dir: str
    resource_type: str
    resource_name: str
    attrs: dict[str, HclValue] = Field(default_factory=dict)


class CopyEnvInput(TfDoBaseInput):
    config: TfDoConfig
    src_env: str
    dst_env: str
    selected_run_dirs: list[str]
    edits: list[ModuleCallEdit | ResourceEdit] = Field(default_factory=list)


class CopyEnvResult(BaseModel):
    copied_run_dirs: list[Path] = Field(default_factory=list)
    edited_run_dirs: list[Path] = Field(default_factory=list)


def _to_raw_attrs(attrs: dict[str, HclValue]) -> dict[str, Any]:
    return {k: _hcl_value_to_raw(v) for k, v in attrs.items()}


def derive_run_dir_pattern(config: TfDoConfig) -> DiscoveryPattern:
    last_segment = config.run_dir_discovery.strip("/").rsplit("/", 1)[-1]
    return parse_discovery_pattern(last_segment)


def _apply_edit_to_file(text: str, edit: ModuleCallEdit | ResourceEdit) -> str:
    raw = _to_raw_attrs(edit.attrs)
    if isinstance(edit, ModuleCallEdit):
        return update_module_block(text, edit.module_name, lambda a, r=raw: a.update(r))
    return update_resource_block(text, edit.resource_type, edit.resource_name, lambda a, r=raw: a.update(r))


def _apply_run_dir_edits(dst_dir: Path, edits_by_run_dir: dict[str, list[ModuleCallEdit | ResourceEdit]]) -> list[Path]:
    edited: list[Path] = []
    for run_dir_name, run_edits in edits_by_run_dir.items():
        dest = dst_dir / run_dir_name
        touched = False
        for edit in run_edits:
            for tf_file in sorted(dest.glob("*.tf")):
                text = tf_file.read_text()
                try:
                    new_text = _apply_edit_to_file(text, edit)
                except ValueError:
                    continue
                if new_text != text:
                    ensure_parents_write_text(tf_file, new_text)
                    touched = True
        if touched:
            edited.append(dest)
    return edited


def copy_env(input_model: CopyEnvInput) -> CopyEnvResult:
    settings = input_model.settings
    work_dir = settings.work_dir
    base = input_model.config.env_base_dir(work_dir)
    src_dir = base / input_model.src_env
    dst_dir = base / input_model.dst_env

    if not src_dir.is_dir():
        raise SrcEnvNotFoundError(f"Source env not found: {src_dir}")
    if dst_dir.exists():
        raise DstEnvExistsError(f"Destination env already exists: {dst_dir}")

    dst_dir.mkdir(parents=True)

    pattern = derive_run_dir_pattern(input_model.config)
    discovered = discover_run_dirs(src_dir, pattern, require_backend=False)
    selected_set = set(input_model.selected_run_dirs)

    copied: list[Path] = []
    for rd in discovered:
        if rd.relative_path not in selected_set:
            continue
        dest = dst_dir / rd.relative_path
        shutil.copytree(rd.path, dest)
        copied.append(dest)

    tfdo_yaml_src = src_dir / "tfdo.yaml"
    if tfdo_yaml_src.is_file():
        shutil.copy2(tfdo_yaml_src, dst_dir / "tfdo.yaml")

    edits_by_run_dir: dict[str, list[ModuleCallEdit | ResourceEdit]] = {}
    for edit in input_model.edits:
        edits_by_run_dir.setdefault(edit.run_dir, []).append(edit)

    edited = _apply_run_dir_edits(dst_dir, edits_by_run_dir)

    for edited_dir in edited:
        terraform_fmt(edited_dir, settings.binary)

    logger.info("Env copied. Run `tfdo check` to ensure it is ready!")
    return CopyEnvResult(copied_run_dirs=copied, edited_run_dirs=edited)
