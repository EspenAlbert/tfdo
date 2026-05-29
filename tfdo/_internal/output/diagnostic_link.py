from __future__ import annotations

import re

from tfdo._internal.output.stream_models import DiagnosticBody

_INSTANCE_INDEX = re.compile(r"\[[^\]]*\]$")
_RESOURCE_CONTEXT = re.compile(
    r'^\s*resource\s+"(?P<type>[^"]+)"\s+"(?P<name>[^"]+)"',
)
_DATA_CONTEXT = re.compile(
    r'^\s*data\s+"(?P<type>[^"]+)"\s+"(?P<name>[^"]+)"',
)


def strip_resource_instance_index(addr: str) -> str:
    return _INSTANCE_INDEX.sub("", addr)


def parse_snippet_context(context: str) -> str | None:
    match _RESOURCE_CONTEXT.match(context):
        case None:
            pass
        case m:
            return f"{m['type']}.{m['name']}"
    match _DATA_CONTEXT.match(context):
        case None:
            return None
        case m:
            return f"data.{m['type']}.{m['name']}"


def addr_matches_type_name_suffix(addr: str, type_name_suffix: str) -> bool:
    base = strip_resource_instance_index(addr)
    if base == type_name_suffix:
        return True
    return base.endswith(f".{type_name_suffix}")


def resolve_diagnostic_addr(
    diagnostic: DiagnosticBody,
    candidate_addrs: frozenset[str],
) -> str | None:
    if diagnostic.address and diagnostic.address in candidate_addrs:
        return diagnostic.address
    if diagnostic.snippet is None or diagnostic.snippet.context is None:
        return None
    suffix = parse_snippet_context(diagnostic.snippet.context)
    if suffix is None:
        return None
    matches = [addr for addr in candidate_addrs if addr_matches_type_name_suffix(addr, suffix)]
    if len(matches) == 1:
        return matches[0]
    return None
