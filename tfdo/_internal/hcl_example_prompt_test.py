from __future__ import annotations

import pytest

from tfdo._internal.hcl_example_prompt import _parse_user_hcl_value, _strip_quotes
from tfdo._internal.hcl_roundtrip import HclAttrRef, HclExpression, HclLiteral, HclVarRef


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Plain string — system should add quotes in HCL output
        ("new-name", HclLiteral("new-name")),
        ("  new-name  ", HclLiteral("new-name")),
        # User explicitly quoted — strip the surrounding quotes
        ('"new-name"', HclLiteral("new-name")),
        # var refs — no quotes in HCL output
        ("var.project_name", HclVarRef("var.project_name")),
        ("local.prefix", HclVarRef("local.prefix")),
        # attr refs
        ("module.vpc.id", HclAttrRef("module.vpc.id")),
        ("data.aws_region.current.name", HclAttrRef("data.aws_region.current.name")),
        ("each.value", HclAttrRef("each.value")),
        # template expression
        ("${var.org_id}", HclExpression("var.org_id")),
        ("${module.vpc.id}", HclExpression("module.vpc.id")),
    ],
)
def test_parse_user_hcl_value(raw: str, expected) -> None:
    assert _parse_user_hcl_value(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ('"new-name"', "new-name"),
        ("new-name", "new-name"),
        ('  "new-name"  ', "new-name"),
    ],
)
def test_strip_quotes(raw: str, expected: str) -> None:
    assert _strip_quotes(raw) == expected
