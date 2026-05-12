from __future__ import annotations

from pathlib import Path

import pytest

from tfdo._internal.hcl_entity_parser import TfModuleCall
from tfdo._internal.hcl_example_prompt import _editable_fields, _parse_user_hcl_value, _strip_quotes
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


@pytest.mark.parametrize(
    "value, expected",
    [
        (HclLiteral("single-region-sharded"), "single-region-sharded"),
        (HclLiteral(42), "42"),
        (HclLiteral(True), "True"),
        (HclVarRef("var.project_id"), "${var.project_id}"),
        (HclAttrRef("module.cluster.id"), "module.cluster.id"),
    ],
)
def test_hcl_value_display_bare_string(value, expected: str) -> None:
    from tfdo._internal.hcl_example_prompt import _hcl_value_display

    assert _hcl_value_display(value) == expected


def test_editable_fields_skips_dict_and_list_attrs() -> None:
    module = TfModuleCall(
        file_path=Path("main.tf"),
        name="my_module",
        source="../..",
        attrs={
            "name": HclLiteral("my-project"),
            "tags": {"env": HclLiteral("dev")},
            "cidrs": [HclLiteral("10.0.0.0/8")],
        },
    )
    fields = _editable_fields(module, idx=0)
    field_names = {f.field for f in fields}
    assert "name" in field_names
    assert "tags" not in field_names
    assert "cidrs" not in field_names
