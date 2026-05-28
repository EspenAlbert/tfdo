from pathlib import Path
from unittest.mock import MagicMock, patch

from tfdo._internal.core import destroy_logic, lifecycle_shell, plan_logic
from tfdo._internal.models import DestroyInput, DestroyResult, PlanResult
from tfdo._internal.output import plan_artifacts
from tfdo._internal.settings import InteractiveMode, TfDoSettings


def _destroy_input(work_dir: Path, **kwargs) -> DestroyInput:
    settings = kwargs.pop("settings", None) or TfDoSettings(work_dir=work_dir, interactive=InteractiveMode.ALWAYS)
    return DestroyInput(settings=settings, **kwargs)


@patch(f"{plan_logic.__name__}.{plan_logic.plan_and_render.__name__}")
@patch(f"{lifecycle_shell.__name__}.{lifecycle_shell.run_lifecycle.__name__}")
def test_passthrough_skips_plan_and_render(passthrough_mock: MagicMock, plan_mock: MagicMock, tmp_path: Path) -> None:
    passthrough_mock.return_value = DestroyResult(exit_code=0)
    settings = TfDoSettings(work_dir=tmp_path, passthrough=True, interactive=InteractiveMode.ALWAYS)
    result = destroy_logic.run_destroy(_destroy_input(tmp_path, settings=settings, auto_approve=True))

    passthrough_mock.assert_called_once()
    plan_mock.assert_not_called()
    assert result.exit_code == 0


@patch(f"{destroy_logic.__name__}.{destroy_logic._apply_saved_plan.__name__}")
@patch(f"{plan_artifacts.__name__}.{plan_artifacts.plan_bin_path.__name__}")
@patch(f"{plan_logic.__name__}.{plan_logic.plan_and_render.__name__}")
def test_auto_approve_applies_saved_plan(
    plan_mock: MagicMock, bin_path_mock: MagicMock, apply_mock: MagicMock, tmp_path: Path
) -> None:
    plan_mock.return_value = PlanResult(exit_code=0)
    bin_path_mock.return_value = MagicMock(is_file=lambda: True)
    apply_mock.return_value = DestroyResult(exit_code=0)

    result = destroy_logic.run_destroy(_destroy_input(tmp_path, auto_approve=True))

    apply_mock.assert_called_once()
    assert result.exit_code == 0


@patch(f"{destroy_logic.__name__}.{destroy_logic._apply_saved_plan.__name__}")
@patch(f"{destroy_logic.__name__}.{destroy_logic._confirm_destroy.__name__}", return_value=False)
@patch(f"{plan_artifacts.__name__}.{plan_artifacts.plan_bin_path.__name__}")
@patch(f"{plan_logic.__name__}.{plan_logic.plan_and_render.__name__}")
def test_declined_destroy_exits_zero_without_apply(
    plan_mock: MagicMock,
    bin_path_mock: MagicMock,
    _confirm_mock: MagicMock,
    apply_mock: MagicMock,
    tmp_path: Path,
) -> None:
    plan_mock.return_value = PlanResult(exit_code=0)
    bin_path_mock.return_value = MagicMock(is_file=lambda: True)

    result = destroy_logic.run_destroy(_destroy_input(tmp_path))

    apply_mock.assert_not_called()
    assert result.exit_code == 0


@patch(f"{destroy_logic.__name__}.failure_output.report_lifecycle_failure")
@patch(f"{destroy_logic.__name__}.{destroy_logic._apply_saved_plan.__name__}")
@patch(f"{plan_artifacts.__name__}.{plan_artifacts.plan_bin_path.__name__}")
@patch(f"{plan_logic.__name__}.{plan_logic.plan_and_render.__name__}")
def test_destroy_failure_reports_stderr(
    plan_mock: MagicMock,
    bin_path_mock: MagicMock,
    apply_mock: MagicMock,
    report_mock: MagicMock,
    tmp_path: Path,
) -> None:
    plan_mock.return_value = PlanResult(exit_code=0)
    bin_path_mock.return_value = MagicMock(is_file=lambda: True)
    apply_mock.return_value = DestroyResult(exit_code=1, stderr="destroy failed")

    result = destroy_logic.run_destroy(_destroy_input(tmp_path, auto_approve=True))

    report_mock.assert_called_once()
    assert result.exit_code == 1
