import logging
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tfdo._internal.inspect import cmd_inspect  # noqa: F401
from tfdo._internal.typer_app import app

runner = CliRunner()


def test_inspect_hcl_paths_cmd_json(tmp_path: Path) -> None:
    (tmp_path / "main.tf").write_text('resource "null_resource" "x" {}\n', encoding="utf-8")
    result = runner.invoke(app, ["inspect", "hcl-paths", "--path", str(tmp_path), "--json"])
    assert result.exit_code == 0
    assert "null_resource.x" in result.stdout


def test_inspect_hcl_paths_cmd_logs_rows_and_errors(caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    (tmp_path / "main.tf").write_text('resource "null_resource" "x" { a = 1 }\n', encoding="utf-8")
    (tmp_path / "bad.tf").write_text("not hcl {{\n", encoding="utf-8")
    caplog.set_level(logging.INFO)
    result = runner.invoke(app, ["inspect", "hcl-paths", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "null_resource.x" in caplog.text
    assert "parse error" in caplog.text
