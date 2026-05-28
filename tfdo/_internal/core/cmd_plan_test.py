from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from tfdo._internal.core import plan_logic
from tfdo._internal.models import PlanResult

runner = CliRunner()


def test_plan_cmd_delegates_to_run_plan(tmp_path: Path) -> None:
    from tfdo._internal.typer_app import app

    with patch.object(plan_logic, "run_plan", return_value=PlanResult(exit_code=0)) as run_mock:
        result = runner.invoke(app, ["--work-dir", str(tmp_path), "plan"])
    assert result.exit_code == 0
    run_mock.assert_called_once()
