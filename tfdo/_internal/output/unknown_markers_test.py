from __future__ import annotations

from tfdo._internal.output.models import OutputChange
from tfdo._internal.output.plan_filters import KNOWN_AFTER_APPLY
from tfdo._internal.output.plan_renderer import _format_output_section, _output_value_text
from tfdo._internal.output.unknown_markers import has_unknown_values


def test_has_unknown_values_scalar_and_structured() -> None:
    assert not has_unknown_values(False)
    assert not has_unknown_values(None)
    assert has_unknown_values(True)
    assert has_unknown_values([True])
    assert not has_unknown_values([False])
    assert has_unknown_values([False, True, False])
    assert has_unknown_values({"id": True})
    assert not has_unknown_values({})


def test_output_value_text_list_after_unknown() -> None:
    change = OutputChange(actions=["create"], after=["subnet-1"], after_unknown=[True])
    assert _output_value_text(change) == KNOWN_AFTER_APPLY


def test_format_output_section_list_after_unknown() -> None:
    changes = {
        "subnet_ids": OutputChange(actions=["create"], after=["subnet-1"], after_unknown=[True]),
    }
    lines = _format_output_section(
        changes,
        terminal_width=80,
        show_unknown_outputs=True,
    )
    assert any("subnet_ids" in line for line in lines)
