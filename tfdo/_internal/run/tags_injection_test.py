from __future__ import annotations

import json
from pathlib import Path

from tfdo._internal.config.enums import TagsInject
from tfdo._internal.run.tags_injection import (
    TAGS_TFVARS_FILENAME,
    has_tags_variable,
    resolve_tags_injection,
    write_tags_var_file,
)

TF_TAGS_MAP_STRING = 'variable "tags" {\n  type = map(string)\n}\n'
TF_TAGS_STRING = 'variable "tags" {\n  type = string\n}\n'
TF_TAGS_NO_TYPE = 'variable "tags" {}\n'
TF_NO_VARIABLES = 'resource "aws_instance" "example" {\n  ami = "abc"\n}\n'


def test_has_tags_variable_map_string(tmp_path: Path):
    (tmp_path / "vars.tf").write_text(TF_TAGS_MAP_STRING)
    assert has_tags_variable(tmp_path)


def test_has_tags_variable_wrong_type(tmp_path: Path):
    (tmp_path / "vars.tf").write_text(TF_TAGS_STRING)
    assert not has_tags_variable(tmp_path)


def test_has_tags_variable_no_type(tmp_path: Path):
    (tmp_path / "vars.tf").write_text(TF_TAGS_NO_TYPE)
    assert not has_tags_variable(tmp_path)


def test_has_tags_variable_no_variables(tmp_path: Path):
    (tmp_path / "main.tf").write_text(TF_NO_VARIABLES)
    assert not has_tags_variable(tmp_path)


def test_has_tags_variable_unparseable(tmp_path: Path):
    (tmp_path / "bad.tf").write_text("{{{{invalid hcl")
    assert not has_tags_variable(tmp_path)


def test_write_tags_var_file(tmp_path: Path):
    tags = {"env": "dev", "app": "api"}
    path = write_tags_var_file(tags, tmp_path)
    assert path.name == TAGS_TFVARS_FILENAME
    content = json.loads(path.read_text())
    assert content == {"tags": {"env": "dev", "app": "api"}}


def test_resolve_tags_injection_always_with_variable(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "vars.tf").write_text(TF_TAGS_MAP_STRING)
    output_dir = tmp_path / "output"
    result = resolve_tags_injection(run_dir, {"env": "dev"}, TagsInject.ALWAYS, output_dir)
    assert result is not None
    content = json.loads(result.read_text())
    assert content == {"tags": {"env": "dev"}}


def test_resolve_tags_injection_always_no_variable(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "main.tf").write_text(TF_NO_VARIABLES)
    result = resolve_tags_injection(run_dir, {"env": "dev"}, TagsInject.ALWAYS, tmp_path / "output")
    assert result is None


def test_resolve_tags_injection_never(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "vars.tf").write_text(TF_TAGS_MAP_STRING)
    result = resolve_tags_injection(run_dir, {"env": "dev"}, TagsInject.NEVER, tmp_path / "output")
    assert result is None


def test_resolve_tags_injection_empty_tags(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "vars.tf").write_text(TF_TAGS_MAP_STRING)
    output_dir = tmp_path / "output"
    result = resolve_tags_injection(run_dir, {}, TagsInject.ALWAYS, output_dir)
    assert result is not None
    content = json.loads(result.read_text())
    assert content == {"tags": {}}
