from __future__ import annotations

from tfdo._internal.output.diagnostic_link import (
    parse_snippet_context,
    resolve_diagnostic_addr,
    resolve_resource_addr,
    strip_resource_instance_index,
)
from tfdo._internal.output.stream_models import DiagnosticBody, DiagnosticSnippet


def test_strip_instance_index() -> None:
    assert strip_resource_instance_index("aws_instance.web[0]") == "aws_instance.web"
    assert strip_resource_instance_index('module.x["east"]') == "module.x"


def test_parse_snippet_context() -> None:
    assert parse_snippet_context('resource "local_file" "second"') == "local_file.second"
    assert parse_snippet_context('data "aws_ami" "ubuntu"') == "data.aws_ami.ubuntu"


def test_resolve_single_match() -> None:
    diag = DiagnosticBody(
        summary="fail",
        snippet=DiagnosticSnippet(
            code="x",
            start_line=1,
            highlight_start_offset=0,
            highlight_end_offset=1,
            context='resource "local_file" "second"',
        ),
    )
    candidates = frozenset({"random_pet.first", "local_file.second"})
    assert resolve_diagnostic_addr(diag, candidates) == "local_file.second"


def test_ambiguous_snippet_returns_none() -> None:
    diag = DiagnosticBody(
        summary="fail",
        snippet=DiagnosticSnippet(
            code="x",
            start_line=1,
            highlight_start_offset=0,
            highlight_end_offset=1,
            context='resource "aws_instance" "web"',
        ),
    )
    candidates = frozenset({"aws_instance.web[0]", "aws_instance.web[1]"})
    assert resolve_diagnostic_addr(diag, candidates) is None


def test_resolve_resource_addr_precedence() -> None:
    diag = DiagnosticBody(
        summary="fail",
        address="local_file.a",
        snippet=DiagnosticSnippet(
            code="x",
            start_line=1,
            highlight_start_offset=0,
            highlight_end_offset=1,
            context='resource "local_file" "b"',
        ),
    )
    candidates = frozenset({"local_file.a", "local_file.b", "local_file.second"})
    assert resolve_resource_addr(diag, pending_hook_addr="local_file.b", candidate_addrs=candidates) == "local_file.a"
    assert resolve_resource_addr(diag, pending_hook_addr="local_file.b", candidate_addrs=frozenset()) == "local_file.a"
    no_addr = DiagnosticBody(
        summary="fail",
        snippet=DiagnosticSnippet(
            code="x",
            start_line=1,
            highlight_start_offset=0,
            highlight_end_offset=1,
            context='resource "local_file" "second"',
        ),
    )
    assert resolve_resource_addr(no_addr, pending_hook_addr="local_file.second", candidate_addrs=candidates) == (
        "local_file.second"
    )
