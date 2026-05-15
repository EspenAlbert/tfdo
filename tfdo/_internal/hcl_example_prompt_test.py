from __future__ import annotations

from pathlib import Path

import pytest

from tfdo._internal.hcl_entity_parser import TfModuleCall
from tfdo._internal.hcl_example_prompt import _editable_fields, _hcl_value_display, _parse_user_hcl_value, _strip_quotes
from tfdo._internal.hcl_roundtrip import HclAttrRef, HclExpression, HclLiteral, HclVarRef


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Plain string — system should add quotes in HCL output
        ("new-name", HclLiteral(value="new-name")),
        ("  new-name  ", HclLiteral(value="new-name")),
        # User explicitly quoted — strip the surrounding quotes
        ('"new-name"', HclLiteral(value="new-name")),
        # var refs — no quotes in HCL output
        ("var.project_name", HclVarRef(path="var.project_name")),
        ("local.prefix", HclVarRef(path="local.prefix")),
        # attr refs
        ("module.vpc.id", HclAttrRef(path="module.vpc.id")),
        ("data.aws_region.current.name", HclAttrRef(path="data.aws_region.current.name")),
        ("each.value", HclAttrRef(path="each.value")),
        # template expression
        ("${var.org_id}", HclExpression(expression="var.org_id")),
        ("${module.vpc.id}", HclExpression(expression="module.vpc.id")),
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


@pytest.mark.parametrize(
    "value, expected",
    [
        (HclLiteral(value="single-region-sharded"), "single-region-sharded"),
        (HclLiteral(value=42), "42"),
        (HclLiteral(value=True), "True"),
        (HclVarRef(path="var.project_id"), "${var.project_id}"),
        (HclAttrRef(path="module.cluster.id"), "module.cluster.id"),
    ],
)
def test_hcl_value_display_bare_string(value, expected: str) -> None:
    assert _hcl_value_display(value) == expected


def test_editable_fields_skips_dict_and_list_attrs() -> None:
    module = TfModuleCall(
        file_path=Path("main.tf"),
        name="my_module",
        source="../..",
        attrs={
            "name": HclLiteral(value="my-project"),
            "tags": {"env": HclLiteral(value="dev")},
            "cidrs": [HclLiteral(value="10.0.0.0/8")],
        },
    )
    fields = _editable_fields(module, idx=0)
    field_names = {f.field for f in fields}
    assert "name" in field_names
    assert "tags" not in field_names
    assert "cidrs" not in field_names
