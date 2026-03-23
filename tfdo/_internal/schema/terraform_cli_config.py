from __future__ import annotations

import os
import re
from contextlib import suppress
from pathlib import Path

from hcl2.api import loads as hcl2_loads
from zero_3rdparty.file_utils import ensure_parents_write_text

from tfdo._internal.schema.cache import REGISTRY_HOST_PREFIX

TF_CLI_CONFIG_FILE_ENV = "TF_CLI_CONFIG_FILE"

_QUOTED_ASSIGN = re.compile(r'"(?P<key>[^"]+)"\s*=\s*"(?P<val>[^"]*)"')
_DEV_OVERRIDES_START = re.compile(r"\bdev_overrides\s*(?:=\s*)?\{")


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


def _brace_body(text: str, open_brace: int) -> tuple[str, int] | None:
    depth = 0
    i = open_brace
    while i < len(text):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace + 1 : i], i + 1
        i += 1
    return None


# Block-style dev_overrides { "ns/type" = "/path" } is valid for Terraform but not parsed by python-hcl2.
def _collect_dev_overrides_text(text: str, by_norm: dict[str, str], *, config_path: Path) -> None:
    pos = 0
    while m := _DEV_OVERRIDES_START.search(text, pos):
        open_brace = m.end() - 1
        pair = _brace_body(text, open_brace)
        if pair is None:
            raise ValueError(f"unclosed or malformed dev_overrides block in {config_path}")
        body, next_pos = pair
        for am in _QUOTED_ASSIGN.finditer(body):
            _store_override(by_norm, am.group("key"), am.group("val"))
        pos = next_pos


def parse_dev_overrides(config_path: Path) -> dict[str, str]:
    raw_text = config_path.read_text(encoding="utf-8")
    by_norm: dict[str, str] = {}
    hcl2_error: Exception | None = None
    hcl2_parsed = False
    try:
        loaded = hcl2_loads(raw_text)
    except Exception as e:
        hcl2_error = e
    else:
        hcl2_parsed = True
        if isinstance(loaded, dict):
            _collect_from_hcl2_root(loaded, by_norm)

    _collect_dev_overrides_text(raw_text, by_norm, config_path=config_path)

    has_dev_block = _DEV_OVERRIDES_START.search(raw_text) is not None
    if has_dev_block and len(by_norm) == 0:
        if hcl2_parsed:
            return {}
        msg = (
            f"could not read dev_overrides assignments from {config_path}; "
            "use quoted registry source and quoted plugin path, or valid HCL2 object form"
        )
        raise ValueError(msg) from hcl2_error

    if not hcl2_parsed and not has_dev_block:
        raise ValueError(
            f"terraform CLI config at {config_path} is not valid HCL2 (python-hcl2 parse failed)"
        ) from hcl2_error

    return dict(by_norm)


def lookup_plugin_dir(overrides: dict[str, str], *, registry_source: str) -> str | None:
    return overrides.get(normalize_registry_source_key(registry_source))


def subprocess_env_for_schema_temp_dir(*, workspace_root: Path, registry_source: str) -> dict[str, str] | None:
    raw = os.environ.get(TF_CLI_CONFIG_FILE_ENV, "").strip()
    if raw:
        cfg = Path(raw).expanduser()
        if cfg.is_file():
            overrides = parse_dev_overrides(cfg)
            if plugin_dir := lookup_plugin_dir(overrides, registry_source=registry_source):
                ephemeral = workspace_root / "tfdo.dev.tfrc"
                write_minimal_dev_overrides_config(
                    ephemeral,
                    registry_source=registry_source,
                    plugin_dir=plugin_dir,
                )
                return {TF_CLI_CONFIG_FILE_ENV: str(ephemeral.resolve())}
    return None


def write_minimal_dev_overrides_config(
    path: Path,
    *,
    registry_source: str,
    plugin_dir: str,
) -> None:
    esc_src = registry_source.replace("\\", "\\\\").replace('"', '\\"')
    pdir = Path(plugin_dir).expanduser()
    with suppress(OSError):
        pdir = pdir.resolve()
    esc_dir = pdir.as_posix().replace("\\", "\\\\").replace('"', '\\"')
    body = f"""provider_installation {{
  dev_overrides {{
    "{esc_src}" = "{esc_dir}"
  }}
  direct {{}}
}}
"""
    ensure_parents_write_text(path, body)
