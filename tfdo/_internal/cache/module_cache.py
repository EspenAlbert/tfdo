from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote

from zero_3rdparty.file_utils import ensure_parents_write_text

from tfdo._internal.core import terraform_init
from tfdo._internal.models import InitInput, InitResult
from tfdo._internal.settings import TfDoSettings

UNRESOLVED = "unresolved"


def source_safe(source: str) -> str:
    return quote(source, safe="")


def cache_dir(cache_root: Path, source: str, version: str) -> Path:
    return cache_root / "tf_modules" / source_safe(source) / version


def lookup(cache_root: Path, source: str, version: str) -> Path | None:
    d = cache_dir(cache_root, source, version)
    if d.is_dir() and any(d.iterdir()):
        return d
    return None


def _module_stub(source: str, version: str) -> str:
    lines = ['module "x" {', f'  source  = "{source}"']
    if version != UNRESOLVED:
        lines.append(f'  version = "{version}"')
    lines += ["}", ""]
    return "\n".join(lines)


def _manifest_entry(modules_src: Path) -> dict | None:
    manifest = modules_src / "modules.json"
    if not manifest.is_file():
        return None
    data = json.loads(manifest.read_text())
    for entry in data.get("Modules", []):
        if entry.get("Key") == "x":
            return entry
    return None


def _resolved_version(modules_src: Path) -> str | None:
    if entry := _manifest_entry(modules_src):
        return entry.get("Version") or None
    return None


def module_source_dir(cache_path: Path) -> Path:
    """Return the path to the actual module source within a cache directory.

    Terraform stores the module under .terraform/modules/x; since the cache
    copies .terraform/modules → cache_path, the source is at cache_path/x
    (or deeper for monorepo modules).
    """
    if entry := _manifest_entry(cache_path):
        relative = entry.get("Dir", "x").removeprefix(".terraform/modules/")
        return cache_path / relative
    return cache_path / "x"


def _ignore_git(_directory: str, contents: list[str]) -> set[str]:
    return {".git"} if ".git" in contents else set()


def populate(cache_root: Path, source: str, version: str, settings: TfDoSettings) -> Path:
    """Populate the module cache and return the cache directory.

    When ``version`` is a constraint (e.g. ``">= 1.0"``), the directory is keyed
    by that constraint string.  When ``version`` is ``None`` / unset the caller
    passes ``_UNRESOLVED``; terraform resolves the actual version and the result
    is stored under the resolved version number so subsequent lookups are stable.
    """
    if lookup(cache_root, source, version) is not None:
        return cache_dir(cache_root, source, version)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        ensure_parents_write_text(tmp / "main.tf", _module_stub(source, version))
        init_settings = settings.with_work_dir(tmp)
        result: InitResult = terraform_init.init(InitInput(settings=init_settings))
        if result.exit_code != 0:
            raise ValueError(f"terraform init failed for module {source}@{version}: {result.stderr}")
        modules_src = tmp / ".terraform" / "modules"
        if not modules_src.is_dir():
            raise ValueError(f"terraform init did not produce a modules directory for {source}@{version}")
        resolved = _resolved_version(modules_src) if version == UNRESOLVED else version
        effective_version = resolved or version
        if lookup(cache_root, source, effective_version) is not None:
            return cache_dir(cache_root, source, effective_version)
        target = cache_dir(cache_root, source, effective_version)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(modules_src, target, ignore=_ignore_git)
    return target
