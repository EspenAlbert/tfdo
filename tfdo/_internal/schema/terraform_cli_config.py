from __future__ import annotations

import logging
import os
from pathlib import Path

from hcl2.api import loads as hcl2_loads
from zero_3rdparty.file_utils import ensure_parents_write_text

from tfdo._internal.schema.cache import REGISTRY_HOST_PREFIX

logger = logging.getLogger(__name__)

TF_CLI_CONFIG_FILE_ENV = "TF_CLI_CONFIG_FILE"


def normalize_registry_source_key(key: str) -> str:
    k = key.strip()
    if k.startswith(REGISTRY_HOST_PREFIX):
        return k[len(REGISTRY_HOST_PREFIX) :]
    return k


def _store_override(by_norm: dict[str, str], raw_key: str, path: str) -> None:
    by_norm[normalize_registry_source_key(raw_key)] = path


def _collect_from_dev_overrides_body(body: object, by_norm: dict[str, str]) -> None:
    if isinstance(body, dict):
        for raw_key, val in body.items():
            if isinstance(val, str):
                _store_override(by_norm, raw_key, val)
        return
    if isinstance(body, list):
        for item in body:
            if isinstance(item, dict):
                _collect_from_dev_overrides_body(item, by_norm)


def _collect_from_hcl2_root(data: dict[str, object], by_norm: dict[str, str]) -> None:
    blocks = data.get("provider_installation")
    if not isinstance(blocks, list):
        return
    for block in blocks:
        if not isinstance(block, dict):
            continue
        raw = block.get("dev_overrides")
        if raw is None:
            continue
        _collect_from_dev_overrides_body(raw, by_norm)


def parse_dev_overrides(config_path: Path) -> dict[str, str]:
    raw_text = config_path.read_text(encoding="utf-8")
    try:
        data = hcl2_loads(raw_text)
    except Exception:
        logger.warning("failed to parse terraform CLI config %s", config_path)
        return {}
    if not isinstance(data, dict):
        return {}
    by_norm: dict[str, str] = {}
    _collect_from_hcl2_root(data, by_norm)
    return dict(by_norm)


def lookup_plugin_dir(overrides: dict[str, str], *, registry_source: str) -> str | None:
    return overrides.get(normalize_registry_source_key(registry_source))


def subprocess_env_for_schema_temp_dir(*, workspace_root: Path, registry_source: str) -> dict[str, str] | None:
    raw = os.environ.get(TF_CLI_CONFIG_FILE_ENV, "").strip()
    if not raw:
        return None
    cfg = Path(raw).expanduser()
    if not cfg.is_file():
        return None
    overrides = parse_dev_overrides(cfg)
    plugin_dir = lookup_plugin_dir(overrides, registry_source=registry_source)
    if plugin_dir is None:
        return None
    ephemeral = workspace_root / "tfdo.dev.tfrc"
    write_minimal_dev_overrides_config(
        ephemeral,
        registry_source=registry_source,
        plugin_dir=plugin_dir,
    )
    return {TF_CLI_CONFIG_FILE_ENV: str(ephemeral.resolve())}


def write_minimal_dev_overrides_config(
    path: Path,
    *,
    registry_source: str,
    plugin_dir: str,
) -> None:
    esc_src = registry_source.replace("\\", "\\\\").replace('"', '\\"')
    pdir = Path(plugin_dir).expanduser()
    try:
        pdir = pdir.resolve()
    except OSError:
        pass
    esc_dir = pdir.as_posix().replace("\\", "\\\\").replace('"', '\\"')
    body = f"""provider_installation {{
  dev_overrides = {{
    "{esc_src}" = "{esc_dir}"
  }}
  direct {{}}
}}
"""
    ensure_parents_write_text(path, body)
