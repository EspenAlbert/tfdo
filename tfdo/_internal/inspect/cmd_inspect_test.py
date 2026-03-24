import logging
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tfdo._internal.inspect import (
    cmd_inspect,
    resource_usage_logic,
)
from tfdo._internal.inspect.schema_input_classify_logic import SchemaInputClassifyResult
from tfdo._internal.typer_app import app

runner = CliRunner()


def test_inspect_hcl_paths_cmd_json(tmp_path: Path) -> None:
    (tmp_path / "main.tf").write_text('resource "null_resource" "x" {}\n', encoding="utf-8")
    result = runner.invoke(app, ["inspect", "hcl-paths", "--path", str(tmp_path), "--json"])
    assert result.exit_code == 0
    assert "null_resource.x" in result.stdout


def test_inspect_hcl_paths_cmd_json_output_file(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    (tmp_path / "main.tf").write_text('resource "null_resource" "x" {}\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    caplog.set_level(logging.INFO)
    result = runner.invoke(
        app,
        ["inspect", "hcl-paths", "--path", ".", "--json", "-o", "nested/out.json"],
    )
    assert result.exit_code == 0
    out = (tmp_path / "nested" / "out.json").resolve()
    assert str(out) in caplog.text
    assert "Wrote JSON to" in caplog.text
    assert "null_resource.x" in out.read_text(encoding="utf-8")


def test_inspect_hcl_paths_cmd_output_requires_json(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    result = runner.invoke(app, ["inspect", "hcl-paths", "--path", str(tmp_path), "-o", str(out)])
    assert result.exit_code == 1


def test_inspect_resource_usage_cmd_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake(inp: resource_usage_logic.ResourceUsageInput) -> resource_usage_logic.ResourceUsageResult:
        assert inp.exclude_patterns == [".github/*", "tests/*"]
        return resource_usage_logic.ResourceUsageResult(providers={}, classify=SchemaInputClassifyResult())

    monkeypatch.setattr(cmd_inspect, cmd_inspect.inspect_resource_usage.__name__, fake)
    result = runner.invoke(app, ["inspect", "resource-usage", "--path", str(tmp_path), "--provider", "mongodbatlas"])
    assert result.exit_code == 0
    assert '"errors": []' in result.stdout
    out = tmp_path / "ru.json"
    result_o = runner.invoke(
        app,
        ["inspect", "resource-usage", "--path", str(tmp_path), "--provider", "mongodbatlas", "-o", str(out)],
    )
    assert result_o.exit_code == 0
    assert '"errors": []' in out.read_text(encoding="utf-8")


def test_inspect_hcl_paths_cmd_logs_rows_and_errors(caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    (tmp_path / "main.tf").write_text('resource "null_resource" "x" { a = 1 }\n', encoding="utf-8")
    (tmp_path / "bad.tf").write_text("not hcl {{\n", encoding="utf-8")
    caplog.set_level(logging.INFO)
    result = runner.invoke(app, ["inspect", "hcl-paths", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "null_resource.x" in caplog.text
    assert "parse error" in caplog.text
