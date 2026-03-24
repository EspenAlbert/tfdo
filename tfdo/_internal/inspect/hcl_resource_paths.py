from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hcl2.api import load as hcl2_load
from pydantic import BaseModel, Field

from tfdo._internal.core.tf_files import iter_tf_files

_TERRAFORM_META_PATHS: frozenset[str] = frozenset(
    {"connection", "count", "depends_on", "for_each", "lifecycle", "provider", "provisioner"}
)
_TERRAFORM_META_PREFIXES: tuple[str, ...] = ("lifecycle.", "provisioner.", "connection.")


class HclParseError(BaseModel):
    path: Path
    message: str
    line: int | None = None
    column: int | None = None


class ResourcePathsRow(BaseModel):
    file: Path
    address: str
    attribute_paths: list[str] = Field(default_factory=list)


class HclResourcePathsResult(BaseModel):
    rows: list[ResourcePathsRow] = Field(default_factory=list)
    errors: list[HclParseError] = Field(default_factory=list)

    def to_canonical_json(self, *, error_paths_relative_to: Path | None = None) -> str:
        errors_out: list[dict[str, Any]] = []
        root_resolved = error_paths_relative_to.resolve() if error_paths_relative_to is not None else None
        for e in self.errors:
            out_path = e.path
            if root_resolved is not None:
                try:
                    out_path = e.path.resolve().relative_to(root_resolved)
                except ValueError:
                    out_path = e.path
            errors_out.append(e.model_copy(update={"path": out_path}).model_dump(mode="json", exclude_none=True))
        payload = {
            "errors": errors_out,
            "rows": [r.model_dump(mode="json") for r in self.rows],
        }
        return json.dumps(payload, indent=2, sort_keys=True)


def collect_resource_argument_paths(root: Path) -> HclResourcePathsResult:
    root_resolved = root.resolve()
    acc: dict[tuple[Path, str], set[str]] = {}
    errors: list[HclParseError] = []
    for path in iter_tf_files(root):
        rel_file = path.resolve().relative_to(root_resolved)
        try:
            with path.open(encoding="utf-8") as f:
                parsed = hcl2_load(f)
        except Exception as exc:
            errors.append(_to_parse_error(path, exc))
            continue
        _merge_parsed_into_file(parsed, rel_file, acc)
    rows = [ResourcePathsRow(file=f, address=a, attribute_paths=sorted(paths)) for (f, a), paths in sorted(acc.items())]
    errors.sort(key=lambda e: (e.path, e.message))
    return HclResourcePathsResult(rows=rows, errors=errors)


def _is_terraform_meta_path(path: str) -> bool:
    if path in _TERRAFORM_META_PATHS:
        return True
    return any(path.startswith(p) for p in _TERRAFORM_META_PREFIXES)


def _filter_meta_paths(paths: set[str]) -> set[str]:
    return {p for p in paths if not _is_terraform_meta_path(p)}


def _to_parse_error(path: Path, exc: BaseException) -> HclParseError:
    line = getattr(exc, "line", None)
    column = getattr(exc, "column", None)
    if isinstance(line, int) and line < 1:
        line = None
    if isinstance(column, int) and column < 1:
        column = None
    return HclParseError(path=path, message=str(exc), line=line, column=column)


def _merge_parsed_into_file(parsed: dict[str, Any], rel_file: Path, acc: dict[tuple[Path, str], set[str]]) -> None:
    for top in parsed.get("resource") or []:
        if not isinstance(top, dict):
            continue
        for rtype, labels_obj in top.items():
            if not isinstance(labels_obj, dict):
                continue
            for label, body in labels_obj.items():
                if not isinstance(body, dict):
                    continue
                addr = f"{rtype}.{label}"
                attr_paths = _filter_meta_paths(_paths_from_resource_body(body))
                key = (rel_file, addr)
                acc.setdefault(key, set()).update(attr_paths)


def _paths_from_resource_body(body: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for key, value in body.items():
        if key == "dynamic":
            paths.update(_paths_from_dynamic(value))
            continue
        if _is_nested_block_list(value):
            paths.update(_paths_from_nested_block(key, value))
            continue
        if isinstance(value, dict) and value:
            expanded = _paths_from_inline_object(key, value)
            paths.update(expanded or {key})
            continue
        paths.add(key)
    return paths


def _is_nested_block_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(x, dict) for x in value)


def _paths_from_inline_object(parent: str, obj: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for subkey, subval in obj.items():
        if _is_nested_block_list(subval):
            continue
        out.add(f"{parent}.{subkey}")
    return out


def _paths_from_nested_block(block_type: str, blocks: list[Any]) -> set[str]:
    out: set[str] = set()
    for block in blocks:
        if not isinstance(block, dict):
            continue
        for arg, val in block.items():
            if _is_nested_block_list(val):
                continue
            out.add(f"{block_type}.{arg}")
    return out


def _paths_from_dynamic(value: Any) -> set[str]:
    out: set[str] = set()
    if not isinstance(value, list):
        return out
    for item in value:
        if not isinstance(item, dict):
            continue
        for block_type, dyn_body in item.items():
            out.update(_paths_from_dynamic_block(block_type, dyn_body))
    return out


def _paths_from_dynamic_block(block_type: str, dyn_body: Any) -> set[str]:
    out: set[str] = set()
    if not isinstance(dyn_body, dict):
        return out
    contents = dyn_body.get("content")
    if not isinstance(contents, list):
        return out
    for content_block in contents:
        if not isinstance(content_block, dict):
            continue
        for arg, val in content_block.items():
            prefix = f"{block_type}.{arg}"
            if _is_nested_block_list(val):
                continue
            if isinstance(val, dict) and val:
                expanded = _paths_from_inline_object(prefix, val)
                out.update(expanded or {prefix})
                continue
            out.add(prefix)
    return out
