import logging

import pytest
from typer.testing import CliRunner

from tfdo._internal.schema import cmd_schema
from tfdo._internal.schema.inspect_logic import SchemaShowResult
from tfdo._internal.schema.models import ResourceSchema, SchemaBlock
from tfdo._internal.typer_app import app

runner = CliRunner()
_schema_show_cmd = cmd_schema.schema_show


def test_schema_show_cmd_exits_on_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise ValueError("bad input")

    monkeypatch.setattr(cmd_schema, _schema_show_cmd.__name__, boom)
    result = runner.invoke(app, ["schema", "show", "--provider", "x", "--source", "a/b"])
    assert result.exit_code == 1


def test_schema_show_cmd_json_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(_inp: object) -> SchemaShowResult:
        return SchemaShowResult(resource_names=["r1", "r2"])

    monkeypatch.setattr(cmd_schema, _schema_show_cmd.__name__, fake)
    result = runner.invoke(app, ["schema", "show", "--provider", "mongodbatlas", "--json"])
    assert result.exit_code == 0
    assert "r1" in result.stdout


def test_schema_show_cmd_logs_type_names(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    def fake(_inp: object) -> SchemaShowResult:
        return SchemaShowResult(resource_names=["aa", "bb"])

    monkeypatch.setattr(cmd_schema, _schema_show_cmd.__name__, fake)
    caplog.set_level(logging.INFO)
    result = runner.invoke(app, ["schema", "show", "--provider", "mongodbatlas"])
    assert result.exit_code == 0
    assert "aa" in caplog.text


def test_schema_show_cmd_dumps_resource_json(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = ResourceSchema(version=0, block=SchemaBlock(attributes={}))

    def fake(_inp: object) -> SchemaShowResult:
        return SchemaShowResult(resource_names=["r"], resource=resource)

    monkeypatch.setattr(cmd_schema, _schema_show_cmd.__name__, fake)
    result = runner.invoke(
        app,
        ["schema", "show", "--provider", "mongodbatlas", "--resource", "r"],
    )
    assert result.exit_code == 0
    assert '"version": 0' in result.stdout
