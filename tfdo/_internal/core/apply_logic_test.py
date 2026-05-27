from pathlib import Path
from unittest.mock import MagicMock, patch

from tfdo._internal.core import apply_logic, executor, plan_logic
from tfdo._internal.models import ApplyInput, ApplyResult, PlanResult
from tfdo._internal.settings import InteractiveMode, TfDoSettings


def _apply_input(work_dir: Path, **kwargs) -> ApplyInput:
    settings = kwargs.pop("settings", None) or TfDoSettings(work_dir=work_dir, interactive=InteractiveMode.ALWAYS)
    return ApplyInput(settings=settings, **kwargs)


@patch(f"{plan_logic.__name__}.{plan_logic.plan_and_render.__name__}")
@patch(f"{executor.__name__}.{executor._run_lifecycle.__name__}")
def test_passthrough_skips_plan_and_render(passthrough_mock: MagicMock, plan_mock: MagicMock, tmp_path: Path) -> None:
    passthrough_mock.return_value = ApplyResult(exit_code=0)
    settings = TfDoSettings(work_dir=tmp_path, passthrough=True, interactive=InteractiveMode.ALWAYS)
    result = apply_logic.run_apply(_apply_input(tmp_path, settings=settings, auto_approve=True))

    passthrough_mock.assert_called_once()
    plan_mock.assert_not_called()
    assert result.exit_code == 0


@patch(f"{apply_logic.__name__}.{apply_logic._apply_saved_plan.__name__}")
@patch(f"{apply_logic.__name__}.{apply_logic.plan_bin_path.__name__}")
@patch(f"{plan_logic.__name__}.{plan_logic.plan_and_render.__name__}")
def test_auto_approve_applies_saved_plan(
    plan_mock: MagicMock, bin_path_mock: MagicMock, apply_mock: MagicMock, tmp_path: Path
) -> None:
    plan_mock.return_value = PlanResult(exit_code=0)
    bin_path_mock.return_value = MagicMock(is_file=lambda: True)
    apply_mock.return_value = ApplyResult(exit_code=0)

    result = apply_logic.run_apply(_apply_input(tmp_path, auto_approve=True))

    apply_mock.assert_called_once()
    assert result.exit_code == 0


@patch(f"{apply_logic.__name__}.{apply_logic._apply_saved_plan.__name__}")
@patch(f"{apply_logic.__name__}.{apply_logic._confirm_apply.__name__}", return_value=False)
@patch(f"{apply_logic.__name__}.{apply_logic.plan_bin_path.__name__}")
@patch(f"{plan_logic.__name__}.{plan_logic.plan_and_render.__name__}")
def test_declined_apply_exits_zero_without_apply(
    plan_mock: MagicMock,
    bin_path_mock: MagicMock,
    _confirm_mock: MagicMock,
    apply_mock: MagicMock,
    tmp_path: Path,
) -> None:
    plan_mock.return_value = PlanResult(exit_code=0)
    bin_path_mock.return_value = MagicMock(is_file=lambda: True)

    result = apply_logic.run_apply(_apply_input(tmp_path))

    apply_mock.assert_not_called()
    assert result.exit_code == 0


@patch(f"{apply_logic.__name__}.{apply_logic._apply_saved_plan.__name__}")
@patch(f"{plan_logic.__name__}.{plan_logic.plan_and_render.__name__}")
def test_plan_failure_skips_apply(plan_mock: MagicMock, apply_mock: MagicMock, tmp_path: Path) -> None:
    plan_mock.return_value = PlanResult(exit_code=1, stderr="plan failed")

    result = apply_logic.run_apply(_apply_input(tmp_path, auto_approve=True))

    apply_mock.assert_not_called()
    assert result.exit_code == 1
