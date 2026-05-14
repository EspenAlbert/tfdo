from __future__ import annotations

import logging
from pathlib import Path

from tfdo._internal.check import cmd_check
from tfdo._internal.models import DirCheckResult


def test_log_dir_issues_reports_missing_tfvars(caplog) -> None:
    result = DirCheckResult(directory=Path("envs/dev/app"), missing_tfvars=["base_url", "org_id"])
    with caplog.at_level(logging.ERROR, logger=cmd_check.__name__):
        cmd_check._log_dir_issues(result)
    assert "tfvars: missing base_url, org_id" in caplog.text


def test_log_next_steps_shows_hints_when_artifacts_missing(tmp_path: Path, caplog) -> None:
    with caplog.at_level(logging.INFO, logger=cmd_check.__name__):
        cmd_check._log_next_steps(tmp_path)
    assert "Next steps:" in caplog.text
    assert "tfdo sync justfile" in caplog.text
    assert "tfdo sync github" in caplog.text


def test_log_next_steps_is_suppressed_when_artifacts_exist(tmp_path: Path, caplog) -> None:
    (tmp_path / "justfile").write_text('set shell := ["bash", "-cu"]\n')
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    with caplog.at_level(logging.INFO, logger=cmd_check.__name__):
        cmd_check._log_next_steps(tmp_path)
    assert "Next steps:" not in caplog.text
