from __future__ import annotations

from tfdo._internal.hcl_roundtrip import HclLiteral, HclValue, HclVarRef
from tfdo._internal.new import cmd_new as cmd_new_module


def test_split_attrs_empty_configure_all_scalars_pass_through() -> None:
    raw: dict[str, HclValue] = {"a": HclLiteral(value="1"), "b": HclLiteral(value="2")}
    passthrough, customize = cmd_new_module._split_attrs_for_customize(raw, frozenset())
    assert passthrough == raw
    assert customize == []


def test_split_attrs_composite_always_passthrough() -> None:
    raw: dict[str, HclValue] = {"a": {"x": HclLiteral(value="")}, "b": HclLiteral(value="2")}
    passthrough, customize = cmd_new_module._split_attrs_for_customize(raw, frozenset({"a", "b"}))
    assert passthrough["a"] == {"x": HclLiteral(value="")}
    assert customize == [("b", HclLiteral(value="2"))]


def test_split_attrs_partial_customize_preserves_lists() -> None:
    inner: list[HclValue] = [{"k": HclLiteral(value="")}]
    raw: dict[str, HclValue] = {"x": HclLiteral(value="1"), "y": inner, "z": HclLiteral(value="z")}
    passthrough, customize = cmd_new_module._split_attrs_for_customize(raw, frozenset({"x"}))
    assert passthrough == {"y": inner, "z": HclLiteral(value="z")}
    assert customize == [("x", HclLiteral(value="1"))]


def test_scalar_attribute_keys_excludes_collections() -> None:
    attrs: dict[str, HclValue] = {
        "a": HclLiteral(value=""),
        "nested": {},
        "many": [],
        "who": HclVarRef(path="var.x"),
    }
    keys = cmd_new_module._scalar_attribute_keys(attrs)
    assert keys == frozenset({"a", "who"})
