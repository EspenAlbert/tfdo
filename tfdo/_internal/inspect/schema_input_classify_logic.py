from __future__ import annotations

import json
from enum import StrEnum
from functools import total_ordering
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from tfdo._internal.inspect.hcl_resource_paths import HclParseError


class SchemaInputClassifyMode(StrEnum):
    INCLUDED = "included"
    EXCLUDED = "excluded"
    ALL = "all"


@total_ordering
class SchemaInputClassifyRowInput(BaseModel):
    file: Path
    address: str
    schema_input_paths: frozenset[str]
    config_paths: frozenset[str]
    invalid_in_config: frozenset[str] = Field(default_factory=frozenset)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SchemaInputClassifyRowInput):
            return NotImplemented
        return (self.file, self.address) < (other.file, other.address)


class SchemaInputClassifyInput(BaseModel):
    mode: SchemaInputClassifyMode
    errors: list[HclParseError] = Field(default_factory=list)
    rows: list[SchemaInputClassifyRowInput] = Field(default_factory=list)


class SchemaInputClassifyRowResult(BaseModel):
    file: Path
    address: str
    included: list[str] | None = None
    excluded: list[str] | None = None
    unknown_in_config: list[str] | None = None
    invalid_in_config: list[str] | None = None


class SchemaInputClassifyResult(BaseModel):
    errors: list[HclParseError] = Field(default_factory=list)
    rows: list[SchemaInputClassifyRowResult] = Field(default_factory=list)

    def to_canonical_json(self, *, error_paths_relative_to: Path | None = None) -> str:
        payload = schema_input_classify_payload(self, error_paths_relative_to=error_paths_relative_to)
        return json.dumps(payload, indent=2, sort_keys=True)


def schema_input_classify_payload(
    result: SchemaInputClassifyResult,
    *,
    error_paths_relative_to: Path | None = None,
) -> dict[str, Any]:
    root = error_paths_relative_to
    root_resolved = root.resolve() if root is not None else None
    errors_out: list[dict[str, Any]] = []
    for e in result.errors:
        out_path = e.path
        if root_resolved is not None:
            try:
                out_path = e.path.resolve().relative_to(root_resolved)
            except ValueError:
                out_path = e.path
        errors_out.append(e.model_copy(update={"path": out_path}).model_dump(mode="json", exclude_none=True))
    return {
        "errors": errors_out,
        "rows": [r.model_dump(mode="json", exclude_none=True) for r in result.rows],
    }


def classify_schema_inputs(input_model: SchemaInputClassifyInput) -> SchemaInputClassifyResult:
    mode = input_model.mode
    sorted_errors = sorted(input_model.errors, key=lambda e: (str(e.path), e.message))
    sorted_rows_in = sorted(input_model.rows)
    out_rows: list[SchemaInputClassifyRowResult] = []
    for row in sorted_rows_in:
        schema_paths = row.schema_input_paths
        config_paths = row.config_paths
        included = sorted(schema_paths & config_paths)
        excluded = sorted(schema_paths - config_paths)
        unknown = sorted(config_paths - schema_paths)
        if mode is SchemaInputClassifyMode.INCLUDED:
            out_rows.append(SchemaInputClassifyRowResult(file=row.file, address=row.address, included=included))
            continue
        if mode is SchemaInputClassifyMode.EXCLUDED:
            out_rows.append(SchemaInputClassifyRowResult(file=row.file, address=row.address, excluded=excluded))
            continue
        invalid = sorted(row.invalid_in_config)
        out_rows.append(
            SchemaInputClassifyRowResult(
                file=row.file,
                address=row.address,
                included=included,
                excluded=excluded,
                unknown_in_config=unknown or None,
                invalid_in_config=invalid or None,
            )
        )
    return SchemaInputClassifyResult(errors=sorted_errors, rows=out_rows)
