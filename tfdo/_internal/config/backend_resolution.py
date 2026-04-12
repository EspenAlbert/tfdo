from __future__ import annotations

import re
from pathlib import Path

from tfdo._internal.config.config_model import BackendConfig, LocalBackend
from tfdo._internal.run.run_context import RunDirContext

_PLACEHOLDER_RE = re.compile(r"\{(?P<key>[^}]+)\}")
_BUILTINS = frozenset({"name", "path", "repo_owner", "repo_name"})


def resolve_placeholders(template: str, ctx: RunDirContext) -> str:
    builtin_map = {"name": ctx.name, "path": ctx.path, "repo_owner": ctx.repo_owner, "repo_name": ctx.repo_name}

    def _replace(m: re.Match[str]) -> str:
        key = m.group("key")
        if key in _BUILTINS:
            return builtin_map[key]
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


def _resolve_backend(backend: BackendConfig, ctx: RunDirContext) -> BackendConfig:
    updates = {}
    for name, value in backend.model_dump(exclude={"type"}).items():
        if isinstance(value, str):
            updates[name] = resolve_placeholders(value, ctx)
    return backend.model_copy(update=updates) if updates else backend


def resolve_backend_args(backend: BackendConfig, ctx: RunDirContext) -> list[str]:
    resolved = _resolve_backend(backend, ctx)
    match resolved:
        case LocalBackend(path=path):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
    return resolved.config_flags


def resolve_init_backend_args(backend: BackendConfig | None, ctx: RunDirContext) -> list[str]:
    if backend is None:
        return []
    return resolve_backend_args(backend, ctx)
