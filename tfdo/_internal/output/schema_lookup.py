from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Literal, NamedTuple

from tfdo._internal.hcl_read import LOCK_FILENAME, REGISTRY_HOST_PREFIX, parse_lock_file_versions
from tfdo._internal.schema import cache as schema_cache
from tfdo._internal.schema.inspect_logic import pick_provider_key
from tfdo._internal.schema.models import ResourceSchema, SchemaBlock

logger = logging.getLogger(__name__)

CollectionKind = Literal["set", "list"]
RequiredAttrsLookup = Callable[[str, str], frozenset[str]]
CollectionKindLookup = Callable[[str, str, tuple[str | int, ...]], CollectionKind | None]


class SchemaLookups(NamedTuple):
    required_attrs: RequiredAttrsLookup
    collection_kind: CollectionKindLookup


def resource_schema_required_attrs(schema: ResourceSchema) -> frozenset[str]:
    out: set[str] = set()
    for name, attr in (schema.block.attributes or {}).items():
        if attr.required is not True or attr.nested_type is not None:
            continue
        if attr.computed is True and attr.optional is not True:
            continue
        out.add(name)
    return frozenset(out)


def _nesting_to_kind(mode: str | None) -> CollectionKind | None:
    if mode == "set":
        return "set"
    if mode == "list":
        return "list"
    return None


def _resolve_segment(block: SchemaBlock, name: str) -> tuple[SchemaBlock, CollectionKind | None] | None:
    attrs = block.attributes or {}
    if name in attrs:
        attr = attrs[name]
        nested = attr.nested_type
        if nested is None:
            return None
        return nested, _nesting_to_kind(nested.nesting_mode)
    block_types = block.block_types or {}
    if name in block_types:
        bt = block_types[name]
        return bt.block, _nesting_to_kind(bt.nesting_mode)
    return None


def attribute_collection_kind(
    schema: ResourceSchema,
    path: tuple[str | int, ...],
) -> CollectionKind | None:
    if not path:
        return None
    str_indices = [i for i, part in enumerate(path) if isinstance(part, str)]
    if not str_indices:
        return None
    terminal_i = str_indices[-1]
    block = schema.block
    for i, part in enumerate(path):
        if isinstance(part, int):
            continue
        resolved = _resolve_segment(block, part)
        if resolved is None:
            return None
        child_block, kind = resolved
        if i == terminal_i:
            return kind
        block = child_block
    return None


def _cache_paths_for_source_version(schema_cache_dir: Path, source: str, version: str) -> list[Path]:
    parts = source.split("/")
    suffix = Path(*parts) / f"{version}.json"
    suffix_len = len(suffix.parts)
    return sorted(
        p
        for p in schema_cache_dir.rglob(f"{version}.json")
        if len(p.relative_to(schema_cache_dir).parts) >= suffix_len
        and Path(*p.relative_to(schema_cache_dir).parts[-suffix_len:]) == suffix
    )


def _load_schemas_from_cache(
    *,
    schema_cache_dir: Path,
    provider_addr: str,
    source: str,
    version: str,
) -> dict[str, ResourceSchema]:
    matches = _cache_paths_for_source_version(schema_cache_dir, source, version)
    if not matches:
        return {}
    if len(matches) > 1:
        logger.warning(
            "multiple schema cache files for %s %s; using %s (also: %s)",
            source,
            version,
            matches[0],
            ", ".join(str(p) for p in matches[1:]),
        )
    payload = schema_cache.try_read_cached_schema(matches[0])
    if payload is None:
        return {}
    pschemas = payload.get("provider_schemas")
    if not isinstance(pschemas, dict):
        return {}
    local_name = source.rpartition("/")[2]
    try:
        pkey = pick_provider_key(pschemas, local_name=local_name, source=source)
    except ValueError:
        return {}
    entry = pschemas.get(pkey)
    if not isinstance(entry, dict):
        return {}
    rschemas = entry.get("resource_schemas")
    if not isinstance(rschemas, dict):
        return {}
    out: dict[str, ResourceSchema] = {}
    for name, data in rschemas.items():
        if isinstance(data, dict):
            out[name] = ResourceSchema.model_validate(data)
    return out


def _build_schema_index(
    *,
    workspace_root: Path,
    schema_cache_dir: Path,
) -> dict[tuple[str, str], ResourceSchema]:
    lock_path = workspace_root / LOCK_FILENAME
    if not lock_path.is_file():
        return {}
    try:
        versions = parse_lock_file_versions(lock_path)
    except (OSError, ValueError):
        return {}
    index: dict[tuple[str, str], ResourceSchema] = {}
    for provider_addr, version in versions.items():
        if not provider_addr.startswith(REGISTRY_HOST_PREFIX):
            continue
        source = provider_addr.removeprefix(REGISTRY_HOST_PREFIX)
        for resource_type, schema in _load_schemas_from_cache(
            schema_cache_dir=schema_cache_dir,
            provider_addr=provider_addr,
            source=source,
            version=version,
        ).items():
            index[(provider_addr, resource_type)] = schema
    return index


def build_schema_lookups(
    *,
    workspace_root: Path,
    schema_cache_dir: Path,
) -> SchemaLookups:
    index = _build_schema_index(workspace_root=workspace_root, schema_cache_dir=schema_cache_dir)

    def required_attrs(provider_name: str, resource_type: str) -> frozenset[str]:
        schema = index.get((provider_name, resource_type))
        if schema is None:
            return frozenset()
        return resource_schema_required_attrs(schema)

    def collection_kind(
        provider_name: str,
        resource_type: str,
        path: tuple[str | int, ...],
    ) -> CollectionKind | None:
        schema = index.get((provider_name, resource_type))
        if schema is None:
            return None
        return attribute_collection_kind(schema, path)

    return SchemaLookups(required_attrs=required_attrs, collection_kind=collection_kind)
