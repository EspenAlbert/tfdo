"""Shared HCL value types used by both read-only parsing and roundtrip modification.

These types represent parsed HCL attribute values in a structured form.
Import from here when you need the value model classes or the ``parse_hcl_value``
helper without pulling in the full roundtrip machinery.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

_HCL_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class HclLiteral(BaseModel, frozen=True):
    value: Any


class HclVarRef(BaseModel, frozen=True):
    path: str


class HclAttrRef(BaseModel, frozen=True):
    path: str


class HclExpression(BaseModel, frozen=True):
    expression: str


type HclValue = HclLiteral | HclVarRef | HclAttrRef | HclExpression | list["HclValue"] | dict[str, "HclValue"]


def strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def _is_hcl_string(value: str) -> bool:
    return len(value) >= 2 and value[0] == '"' and value[-1] == '"'


def _is_hcl_expression(value: str) -> bool:
    if value.startswith("${") and value.endswith("}"):
        return True
    if "." not in value or " " in value or "/" in value:
        return False
    return all(_HCL_IDENT.match(part) for part in value.split("."))


def _is_attr_reference_path(value: str) -> bool:
    if value.startswith("var."):
        return False
    segments = value.split(".")
    if len(segments) < 2:
        return False
    for segment in segments:
        if not segment:
            return False
        if not (segment[0].isalpha() or segment[0] == "_"):
            return False
        if not all(char.isalnum() or char == "_" for char in segment):
            return False
    return True


def _parse_interpolation(value: str) -> HclVarRef | HclAttrRef | HclExpression:
    expression = value[2:-1].strip()
    if expression.startswith("var."):
        return HclVarRef(path=expression)
    if _is_attr_reference_path(expression):
        return HclAttrRef(path=expression)
    return HclExpression(expression=expression)


def parse_hcl_value(value: Any) -> HclValue:
    if isinstance(value, dict):
        return {key: parse_hcl_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [parse_hcl_value(item) for item in value]
    if isinstance(value, str) and _is_hcl_string(value):
        return HclLiteral(value=strip_wrapping_quotes(value))
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return _parse_interpolation(value)
    return HclLiteral(value=value)
