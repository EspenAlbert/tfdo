from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, NamedTuple

from zero_3rdparty.file_utils import ensure_parents_write_text

from tfdo._internal import hcl_roundtrip
from tfdo._internal.config.config_model import BackendConfig, LocalBackend, S3Backend
from tfdo._internal.hcl_compat import hcl2_loads
from tfdo._internal.run.run_context import RunDirContext

logger = logging.getLogger(__name__)

_PLACEHOLDER_RE = re.compile(r"\{(?P<key>[^}]+)\}")
_BUILTINS = frozenset({"name", "path", "repo_owner", "repo_name"})

_DEFAULT_BACKEND_TF_FILENAME = "backend.tf"


class _BackendTfEdit(NamedTuple):
    tf_path: Path
    original: str
    updated: str


def resolve_placeholders(template: str, ctx: RunDirContext) -> str:
    builtin_map = {"name": ctx.name, "path": ctx.path, "repo_owner": ctx.repo_owner, "repo_name": ctx.repo_name}

    def _replace(m: re.Match[str]) -> str:
        key = m.group("key")
        if key in _BUILTINS:
            if value := builtin_map[key]:
                return value
            return m.group(0)
        if key.startswith("tags."):
            tag_key = key.removeprefix("tags.")
            if tag_key in ctx.tags:
                return ctx.tags[tag_key]
        elif key in ctx.tags:
            return ctx.tags[key]
        return m.group(0)

    result = _PLACEHOLDER_RE.sub(_replace, template)
    if unresolved := _PLACEHOLDER_RE.findall(result):
        available = sorted({*_BUILTINS, *(f"tags.{k}" for k in ctx.tags), *ctx.tags})
        raise ValueError(
            f"unresolved placeholders in {template!r}: {unresolved}. "
            f"Available: {available}. Add the missing key to tags in tfdo.yaml or fix the template"
        )
    return result


def resolve_backend(backend: BackendConfig, ctx: RunDirContext) -> BackendConfig:
    updates = {}
    for name, value in backend.model_dump(exclude={"type"}).items():
        if isinstance(value, str):
            updates[name] = resolve_placeholders(value, ctx)
    return backend.model_copy(update=updates) if updates else backend


def resolve_backend_args(backend: BackendConfig, ctx: RunDirContext) -> list[str]:
    resolved = resolve_backend(backend, ctx)
    match resolved:
        case LocalBackend(path=path):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
    return resolved.config_flags


def resolve_init_backend_args(backend: BackendConfig | None, ctx: RunDirContext) -> list[str]:
    if backend is None:
        return []
    return resolve_backend_args(backend, ctx)


def _sorted_tf_paths(run_dir: Path) -> list[Path]:
    return sorted(run_dir.glob("*.tf"))


def _loads_tf(tf_path: Path) -> dict[str, Any] | None:
    try:
        return hcl2_loads(tf_path.read_text())
    except Exception:
        logger.warning(f"skipping unparseable file: {tf_path}")
        return None


def _file_defines_backend(data: dict[str, Any]) -> bool:
    return any(isinstance(block, dict) and "backend" in block for block in data.get("terraform", []))


def _terraform_exists_without_backend(data: dict[str, Any]) -> bool:
    blocks = data.get("terraform")
    return (
        isinstance(blocks, list)
        and bool(blocks)
        and all(isinstance(block, dict) and "backend" not in block for block in blocks)
    )


def _exclusive_existing_backend_tf_path(run_dir: Path) -> Path | None:
    found: Path | None = None
    for tf_path in _sorted_tf_paths(run_dir):
        if (data := _loads_tf(tf_path)) is None or not _file_defines_backend(data):
            continue
        if found is not None:
            raise ValueError(
                "multiple terraform backend blocks across *.tf files in "
                f"{run_dir}: {found.name}, {tf_path.name}. Keep a single backend block"
            )
        found = tf_path
    return found


def _first_terraform_file_without_backend(run_dir: Path) -> Path | None:
    for tf_path in _sorted_tf_paths(run_dir):
        if (data := _loads_tf(tf_path)) is not None and _terraform_exists_without_backend(data):
            return tf_path
    return None


def _backend_tf_path_for_resolve(run_dir: Path) -> Path:
    if path := _exclusive_existing_backend_tf_path(run_dir):
        return path
    if insert := _first_terraform_file_without_backend(run_dir):
        return insert
    return run_dir / _DEFAULT_BACKEND_TF_FILENAME


def _resolve_backend_tf_content(run_dir: Path, backend: BackendConfig, ctx: RunDirContext) -> _BackendTfEdit | None:
    resolved = resolve_backend(backend, ctx)
    match resolved:
        case S3Backend():
            hcl_type, hcl_config = "s3", resolved.hcl_config
        case LocalBackend(path=p):
            hcl_type, hcl_config = "local", {"path": f'"{p}"'}
        case _:
            return None

    tf_path = _backend_tf_path_for_resolve(run_dir)
    original = tf_path.read_text() if tf_path.is_file() else ""
    try:
        updated = hcl_roundtrip.update_backend_block(original, hcl_type, hcl_config)
    except ValueError:
        updated = hcl_roundtrip.add_backend_block(original, hcl_type, hcl_config)
    return _BackendTfEdit(tf_path, original, updated)


def has_backend_drift(run_dir: Path, backend: BackendConfig, ctx: RunDirContext) -> bool:
    result = _resolve_backend_tf_content(run_dir, backend, ctx)
    if result is None:
        return False
    return result.original != result.updated


def ensure_backend_tf(run_dir: Path, backend: BackendConfig, ctx: RunDirContext) -> bool:
    result = _resolve_backend_tf_content(run_dir, backend, ctx)
    if result is None:
        return False
    if result.updated == result.original:
        return False
    ensure_parents_write_text(result.tf_path, result.updated)
    logger.info(f"updated backend block in {result.tf_path.name} under {run_dir.name}")
    return True
