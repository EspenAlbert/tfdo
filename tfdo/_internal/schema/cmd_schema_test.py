import logging

import pytest
from typer.testing import CliRunner

from tfdo._internal.schema import cmd_schema  # noqa: F401
from tfdo._internal.schema.inspect_logic import SchemaShowResult
from tfdo._internal.schema.models import ResourceSchema, SchemaBlock
from tfdo._internal.typer_app import app

runner = CliRunner()


def test_schema_show_cmd_exits_on_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise ValueError("bad input")

    monkeypatch.setattr("tfdo._internal.schema.cmd_schema.schema_show", boom)
    result = runner.invoke(app, ["schema", "show", "--provider", "x", "--source", "a/b"])
    assert result.exit_code == 1


def test_schema_show_cmd_json_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(_inp: object) -> SchemaShowResult:
        return SchemaShowResult(resource_names=["r1", "r2"])

    monkeypatch.setattr("tfdo._internal.schema.cmd_schema.schema_show", fake)
    result = runner.invoke(app, ["schema", "show", "--provider", "mongodbatlas", "--json"])
    assert result.exit_code == 0
    assert "r1" in result.stdout


def test_schema_show_cmd_logs_type_names(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    def fake(_inp: object) -> SchemaShowResult:
        return SchemaShowResult(resource_names=["aa", "bb"])

    monkeypatch.setattr("tfdo._internal.schema.cmd_schema.schema_show", fake)
    caplog.set_level(logging.INFO)
    result = runner.invoke(app, ["schema", "show", "--provider", "mongodbatlas"])
    assert result.exit_code == 0
    assert "aa" in caplog.text


def test_schema_show_cmd_dumps_resource_json(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = ResourceSchema(version=0, block=SchemaBlock(attributes={}))

    def fake(_inp: object) -> SchemaShowResult:
        return SchemaShowResult(resource_names=["r"], resource=resource)

    monkeypatch.setattr("tfdo._internal.schema.cmd_schema.schema_show", fake)
    result = runner.invoke(
        app,
        ["schema", "show", "--provider", "mongodbatlas", "--resource", "r"],
    )
    assert result.exit_code == 0
    assert '"version": 0' in result.stdout
