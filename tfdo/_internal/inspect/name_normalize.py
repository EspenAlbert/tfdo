from __future__ import annotations

import re
from difflib import get_close_matches

from pydantic import BaseModel, Field

_CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")
_ARRAY_RE = re.compile(r"\[\]")
_WILDCARD_SUFFIX_RE = re.compile(r"\.\*$")


def _to_snake(segment: str) -> str:
    return _CAMEL_RE.sub(r"\1_\2", segment).lower()


def normalize_api_path(api_path: str) -> str:
    cleaned = _ARRAY_RE.sub("", api_path)
    cleaned = _WILDCARD_SUFFIX_RE.sub("", cleaned)
    cleaned = cleaned.rstrip(".")
    return ".".join(_to_snake(seg) for seg in cleaned.split(".") if seg)


class NameMapping(BaseModel):
    matched: dict[str, str] = Field(default_factory=dict)
    fuzzy_matched: dict[str, str] = Field(default_factory=dict)
    prefix_matched: dict[str, list[str]] = Field(default_factory=dict)
    api_only: set[str] = Field(default_factory=set)
    tf_only: set[str] = Field(default_factory=set)


def _normalize_api_paths(api_paths: set[str], overrides: dict[str, str]) -> dict[str, str]:
    norm_to_api: dict[str, str] = {}
    for ap in api_paths:
        normed = normalize_api_path(ap)
        normed = overrides.get(normed, normed)
        norm_to_api[normed] = ap
    return norm_to_api


def _match_exact(norm_to_api: dict[str, str], remaining_tf: set[str]) -> dict[str, str]:
    matched: dict[str, str] = {}
    for normed, orig_api in list(norm_to_api.items()):
        if normed in remaining_tf:
            matched[orig_api] = normed
            remaining_tf.discard(normed)
            del norm_to_api[normed]
    return matched


def _match_prefix(norm_to_api: dict[str, str], remaining_tf: set[str]) -> dict[str, list[str]]:
    prefix_matched: dict[str, list[str]] = {}
    for tf_leaf in list(remaining_tf):
        prefix = f"{tf_leaf}."
        children = [n for n in norm_to_api if n.startswith(prefix)]
        if children:
            prefix_matched[tf_leaf] = sorted(norm_to_api[c] for c in children)
            for c in children:
                del norm_to_api[c]
            remaining_tf.discard(tf_leaf)
    return prefix_matched


def _match_fuzzy(norm_to_api: dict[str, str], remaining_tf: set[str], cutoff: float) -> dict[str, str]:
    fuzzy: dict[str, str] = {}
    tf_list = sorted(remaining_tf)
    for normed in list(norm_to_api.keys()):
        hits = get_close_matches(normed, tf_list, n=1, cutoff=cutoff)
        if hits:
            fuzzy[norm_to_api[normed]] = hits[0]
            remaining_tf.discard(hits[0])
            tf_list = sorted(remaining_tf)
            del norm_to_api[normed]
    return fuzzy


def build_name_mapping(
    api_paths: set[str],
    tf_paths: set[str],
    overrides: dict[str, str] | None = None,
    *,
    similarity_cutoff: float = 0.8,
) -> NameMapping:
    norm_to_api = _normalize_api_paths(api_paths, overrides or {})
    remaining_tf = set(tf_paths)
    matched = _match_exact(norm_to_api, remaining_tf)
    prefix_matched = _match_prefix(norm_to_api, remaining_tf)
    fuzzy_matched = _match_fuzzy(norm_to_api, remaining_tf, similarity_cutoff)
    api_only = set(norm_to_api.values())
    return NameMapping(
        matched=matched,
        fuzzy_matched=fuzzy_matched,
        prefix_matched=prefix_matched,
        api_only=api_only,
        tf_only=remaining_tf,
    )
