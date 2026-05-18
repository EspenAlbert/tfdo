from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from ask_shell.shell import ShellRun

from tfdo._internal.core.plan_subprocess import show_plan_json
from tfdo._internal.output.models import PlanOutput
from tfdo._internal.settings import TfDoSettings

_PATCH_SHOW_RUN = "tfdo._internal.core.plan_subprocess.run_and_wait"


def _settings(tmp_path: Path) -> TfDoSettings:
    return TfDoSettings.for_testing(tmp_path, work_dir=tmp_path)


def _mock_run(*, exit_code: int = 0, stdout: str = "") -> MagicMock:
    run = MagicMock(spec=ShellRun)
    run.exit_code = exit_code
    run.stdout = stdout
    run.stdout_one_line = stdout
    run.parse_output.return_value = PlanOutput.model_validate(json.loads(stdout))
    return run


def test_show_plan_json_uses_ansi_content_false(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    plan_bin = tmp_path / "tfplan"
    plan_bin.write_bytes(b"plan")
    stdout = json.dumps({"format_version": "1.2", "errored": False})
    run = _mock_run(stdout=stdout)

    with patch(_PATCH_SHOW_RUN, return_value=run) as mock_run:
        plan_output, exit_code = show_plan_json(settings, plan_bin)

    assert exit_code == 0
    assert plan_output is not None
    assert plan_output.format_version == "1.2"
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["ansi_content"] is False
    run.parse_output.assert_called_once_with(PlanOutput)


def test_show_plan_json_parses_sensitive_true_tokens(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    plan_bin = tmp_path / "tfplan"
    plan_bin.write_bytes(b"plan")
    stdout = json.dumps(
        {
            "format_version": "1.2",
            "errored": False,
            "prior_state": {
                "values": {
                    "sensitive_values": {
                        "users": [
                            {"roles": [{"org_roles": [True], "project_role_assignments": [{"project_roles": [True]}]}]}
                        ]
                    }
                }
            },
        }
    )
    run = _mock_run(stdout=stdout)

    with patch(_PATCH_SHOW_RUN, return_value=run):
        plan_output, exit_code = show_plan_json(settings, plan_bin)

    assert exit_code == 0
    assert plan_output is not None
    assert "[true]" in stdout
