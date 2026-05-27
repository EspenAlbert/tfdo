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
ComputedOnlyLookup = Callable[[str, str, tuple[str | int, ...]], bool | None]


class SchemaLookups(NamedTuple):
    required_attrs: RequiredAttrsLookup
    collection_kind: CollectionKindLookup
    computed_at_path: ComputedOnlyLookup


class SchemaFieldInfo(NamedTuple):
    is_block: bool
    nesting_mode: str | None


class _Segment(NamedTuple):
    block: SchemaBlock
    nesting_mode: str | None
    is_block: bool


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


def _resolve_segment(block: SchemaBlock, name: str) -> _Segment | None:
    attrs = block.attributes or {}
    if name in attrs:
        attr = attrs[name]
        nested = attr.nested_type
        if nested is None:
            return None
        return _Segment(nested, nested.nesting_mode, False)
    block_types = block.block_types or {}
    if name in block_types:
        bt = block_types[name]
        return _Segment(bt.block, bt.nesting_mode, True)
    return None


def schema_field_at_path(schema: ResourceSchema, path: tuple[str | int, ...]) -> SchemaFieldInfo | None:
    if not path:
        return None
    str_parts = [part for part in path if isinstance(part, str)]
    if not str_parts:
        return None
    block = schema.block
    segment: _Segment | None = None
    for name in str_parts:
        segment = _resolve_segment(block, name)
        if segment is None:
            return None
        block = segment.block
    if segment is None:
        return None
    return SchemaFieldInfo(is_block=segment.is_block, nesting_mode=segment.nesting_mode)


def attribute_computed_at_path(
    schema: ResourceSchema,
    path: tuple[str | int, ...],
) -> bool | None:
    if not path:
        return None
    str_parts = [part for part in path if isinstance(part, str)]
    if not str_parts:
        return None
    terminal = str_parts[-1]
    block = schema.block
    for part in path:
        if isinstance(part, int):
            continue
        if part == terminal:
            attr = (block.attributes or {}).get(part)
            if attr is None:
                return None
            if attr.computed is True:
                return True
            if attr.computed is False:
                return False
            return None
        resolved = _resolve_segment(block, part)
        if resolved is None:
            return None
        block = resolved.block
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
        if i == terminal_i:
            return _nesting_to_kind(resolved.nesting_mode)
        block = resolved.block
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

    def computed_at_path(
        provider_name: str,
        resource_type: str,
        path: tuple[str | int, ...],
    ) -> bool | None:
        schema = index.get((provider_name, resource_type))
        if schema is None:
            return None
        str_path = tuple(part for part in path if isinstance(part, str))
        if not str_path:
            return None
        return attribute_computed_at_path(schema, str_path)

    return SchemaLookups(
        required_attrs=required_attrs,
        collection_kind=collection_kind,
        computed_at_path=computed_at_path,
    )


def build_schema_lookups_from_index(
    index: dict[str, ResourceSchema],
) -> SchemaLookups:
    # Fixture index is keyed by resource_type only; provider_name stays in the
    # signature to match SchemaLookups (production uses provider_addr + type).
    def required_attrs(_provider_name: str, resource_type: str) -> frozenset[str]:
        schema = index.get(resource_type)
        if schema is None:
            return frozenset()
        return resource_schema_required_attrs(schema)

    def collection_kind(
        _provider_name: str,
        resource_type: str,
        path: tuple[str | int, ...],
    ) -> CollectionKind | None:
        schema = index.get(resource_type)
        if schema is None:
            return None
        return attribute_collection_kind(schema, path)

    def computed_at_path(
        _provider_name: str,
        resource_type: str,
        path: tuple[str | int, ...],
    ) -> bool | None:
        schema = index.get(resource_type)
        if schema is None:
            return None
        str_path = tuple(part for part in path if isinstance(part, str))
        if not str_path:
            return None
        return attribute_computed_at_path(schema, str_path)

    return SchemaLookups(
        required_attrs=required_attrs,
        collection_kind=collection_kind,
        computed_at_path=computed_at_path,
    )
