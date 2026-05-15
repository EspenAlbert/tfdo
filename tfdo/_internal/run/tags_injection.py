from __future__ import annotations

import json
import logging
from pathlib import Path

from tfdo._internal.config.enums import TagsInject
from tfdo._internal.hcl_read import hcl2_loads

logger = logging.getLogger(__name__)

TAGS_TFVARS_FILENAME = "_tfdo_tags.tfvars.json"
_MAP_STRING_TYPE = "${map(string)}"


def has_tags_variable(directory: Path) -> bool:
    for tf_file in directory.glob("*.tf"):
        if tf_file.is_relative_to(directory / ".terraform"):
            continue
        try:
            data = hcl2_loads(tf_file.read_text())
        except Exception:
            logger.warning(f"skipping unparseable file: {tf_file}")
            continue
        for var_block in data.get("variable", []):
            if "tags" not in var_block:
                continue
            var_def = var_block["tags"]
            if var_def.get("type") == _MAP_STRING_TYPE:
                return True
    return False


def write_tags_var_file(tags: dict[str, str], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / TAGS_TFVARS_FILENAME
    path.write_text(json.dumps({"tags": tags}, indent=2) + "\n")
    return path


def resolve_tags_injection(
    run_dir: Path,
    tags: dict[str, str],
    tags_inject: TagsInject,
    output_dir: Path,
) -> Path | None:
    if tags_inject == TagsInject.NEVER:
        return None
    if not has_tags_variable(run_dir):
        return None
    return write_tags_var_file(tags, output_dir)
