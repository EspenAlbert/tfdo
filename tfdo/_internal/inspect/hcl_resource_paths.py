from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hcl2.api import load as hcl2_load
from pydantic import BaseModel, Field

from tfdo._internal.core.tf_files import iter_tf_files


class HclParseError(BaseModel):
    path: str
    message: str
    line: int | None = None
    column: int | None = None


class ResourcePathsEntry(BaseModel):
    paths: list[str] = Field(default_factory=list)


class HclResourcePathsResult(BaseModel):
    resources: dict[str, ResourcePathsEntry] = Field(default_factory=dict)
    errors: list[HclParseError] = Field(default_factory=list)

    def to_canonical_json(self, *, error_paths_relative_to: Path | None = None) -> str:
        errors_out: list[dict[str, Any]] = []
        root_resolved = error_paths_relative_to.resolve() if error_paths_relative_to is not None else None
        for e in self.errors:
            d = e.model_dump(mode="json", exclude_none=True)
            if root_resolved is not None:
                ep = Path(d["path"])
                try:
                    d["path"] = ep.resolve().relative_to(root_resolved).as_posix()
                except ValueError:
                    pass
            errors_out.append(d)
        payload = {
            "errors": errors_out,
            "resources": {addr: {"paths": entry.paths} for addr, entry in self.resources.items()},
        }
        return json.dumps(payload, indent=2, sort_keys=True)


def collect_resource_argument_paths(root: Path) -> HclResourcePathsResult:
    merged: dict[str, set[str]] = {}
    errors: list[HclParseError] = []
    for path in iter_tf_files(root):
        try:
            with path.open(encoding="utf-8") as f:
                parsed = hcl2_load(f)
        except Exception as exc:
            errors.append(_to_parse_error(path, exc))
            continue
        _merge_parsed_into(parsed, merged)
    resources = {addr: ResourcePathsEntry(paths=sorted(paths)) for addr, paths in sorted(merged.items())}
    errors.sort(key=lambda e: (e.path, e.message))
    return HclResourcePathsResult(resources=resources, errors=errors)


def _to_parse_error(path: Path, exc: BaseException) -> HclParseError:
    line = getattr(exc, "line", None)
    column = getattr(exc, "column", None)
    if isinstance(line, int) and line < 1:
        line = None
    if isinstance(column, int) and column < 1:
        column = None
    return HclParseError(path=str(path), message=str(exc), line=line, column=column)


def _merge_parsed_into(parsed: dict[str, Any], merged: dict[str, set[str]]) -> None:
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
                paths = _paths_from_resource_body(body)
                merged.setdefault(addr, set()).update(paths)


def _paths_from_resource_body(body: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for key, value in body.items():
        if key == "dynamic":
            paths.update(_paths_from_dynamic(value))
            continue
        if _is_nested_block_list(value):
            paths.update(_paths_from_nested_block(key, value))
            continue
        paths.add(key)
    return paths


def _is_nested_block_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(x, dict) for x in value)


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
            if _is_nested_block_list(val):
                continue
            out.add(f"{block_type}.{arg}")
    return out
