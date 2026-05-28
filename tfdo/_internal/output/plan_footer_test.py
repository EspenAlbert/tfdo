from pathlib import Path
from unittest.mock import patch

from tfdo._internal.core import binary
from tfdo._internal.output import plan_footer
from tfdo._internal.output.plan_display import DetailLevel
from tfdo._internal.settings import TfDoSettings

_MODULE = plan_footer.__name__


def test_print_plan_footer_compact(tmp_path: Path) -> None:
    settings = TfDoSettings(work_dir=tmp_path, binary="terraform")
    with patch(f"{_MODULE}.ask_console.print_to_live") as print_mock:
        plan_footer.print_plan_footer(settings, detail=DetailLevel.COMPACT)
    lines = [call.args[0] for call in print_mock.call_args_list]
    bin_path = (tmp_path / ".tfdo" / "plan.bin").resolve()
    json_path = (tmp_path / ".tfdo" / "plan.json").resolve()
    assert lines[0] == f"Full plan:  {binary.resolve_binary(settings)} show {bin_path}"
    assert lines[1] == f"Plan JSON:  {json_path}"
    assert lines[2] == "More depth: tfdo plan --detail full"


def test_print_plan_footer_full_omits_more_depth(tmp_path: Path) -> None:
    settings = TfDoSettings(work_dir=tmp_path)
    with patch(f"{_MODULE}.ask_console.print_to_live") as print_mock:
        plan_footer.print_plan_footer(settings, detail=DetailLevel.FULL)
    assert len(print_mock.call_args_list) == 2


def test_print_plan_footer_skips_passthrough(tmp_path: Path) -> None:
    settings = TfDoSettings(work_dir=tmp_path, passthrough=True)
    with patch(f"{_MODULE}.ask_console.print_to_live") as print_mock:
        plan_footer.print_plan_footer(settings, detail=DetailLevel.COMPACT)
    print_mock.assert_not_called()
