from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from tfdo._internal.core import executor, plan_logic
from tfdo._internal.models import PlanInput, PlanResult
from tfdo._internal.output.models import PlanOutput
from tfdo._internal.output.plan_artifacts import plan_bin_path, plan_json_path
from tfdo._internal.output.testdata_paths import TESTDATA_DIR
from tfdo._internal.settings import TfDoSettings


def _settings(tmp_path: Path) -> TfDoSettings:
    return TfDoSettings.for_testing(tmp_path, work_dir=tmp_path)


def test_run_plan_renders_and_writes_artifacts(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    fixture = TESTDATA_DIR / "01_create_flat.json"
    plan_output = PlanOutput.model_validate(json.loads(fixture.read_text()))
    bin_path = plan_bin_path(tmp_path)
    bin_path.parent.mkdir(parents=True)
    bin_path.write_bytes(b"plan")

    with (
        patch.object(executor, "run_streaming_plan", return_value=PlanResult(exit_code=2)),
        patch.object(executor, "show_plan_json", return_value=(plan_output, 0)),
        patch.object(plan_logic, "render_plan") as render_mock,
        patch.object(plan_logic, "build_schema_lookups") as lookups_mock,
    ):
        result = plan_logic.run_plan(PlanInput(settings=settings))

    assert result.exit_code == 2
    assert plan_json_path(tmp_path).is_file()
    render_mock.assert_called_once()
    lookups_mock.assert_called_once()


def test_run_plan_parse_failure_keeps_plan_exit_code(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    bin_path = plan_bin_path(tmp_path)
    bin_path.parent.mkdir(parents=True)
    bin_path.write_bytes(b"plan")

    with (
        patch.object(executor, "run_streaming_plan", return_value=PlanResult(exit_code=2)),
        patch.object(
            executor,
            "show_plan_json",
            return_value=(PlanOutput(format_version="1.2", errored=False), 0),
        ),
        patch.object(plan_logic, "parse_plan_file", side_effect=json.JSONDecodeError("bad", "doc", 0)),
        patch.object(plan_logic, "render_plan") as render_mock,
    ):
        result = plan_logic.run_plan(PlanInput(settings=settings))

    assert result.exit_code == 2
    render_mock.assert_not_called()


def test_run_plan_exports_user_out(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    bin_path = plan_bin_path(tmp_path)
    bin_path.parent.mkdir(parents=True)
    bin_path.write_bytes(b"tfplan-bytes")
    user_out = tmp_path / "out" / "staging.tfplan"

    with (
        patch.object(executor, "run_streaming_plan", return_value=PlanResult(exit_code=0)),
        patch.object(executor, "show_plan_json", return_value=(None, 1)),
    ):
        plan_logic.run_plan(PlanInput(settings=settings, out=Path("out/staging.tfplan")))

    assert user_out.read_bytes() == b"tfplan-bytes"
