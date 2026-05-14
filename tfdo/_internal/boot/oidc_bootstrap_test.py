from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ask_shell.shell import ShellError

from tfdo._internal.boot import oidc_bootstrap
from tfdo._internal.boot.oidc_bootstrap import (
    _ENTITY_ALREADY_EXISTS,
    _GITHUB_ACTIONS_URL,
    _GITHUB_THUMBPRINT,
    parse_github_remote,
    provision_oidc_provider,
    provision_oidc_role,
)

_MODULE = oidc_bootstrap.__name__
_ACCOUNT_ID = "123456789012"
_ROLE_ARN = f"arn:aws:iam::{_ACCOUNT_ID}:role/my-role"
_EXPECTED_PROVIDER_ARN = f"arn:aws:iam::{_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"


def _make_run(data: dict) -> MagicMock:
    run = MagicMock()
    run.parse_output.return_value = data
    run.stdout_one_line = json.dumps(data)
    return run


def _make_shell_error(message: str) -> ShellError:
    run = MagicMock()
    run.stdout_one_line = message
    run.stdout = message
    run.stderr = message
    return ShellError(run)


def test_provision_oidc_provider_skips_when_already_exists() -> None:
    list_data = {"OpenIDConnectProviderList": [{"Arn": _EXPECTED_PROVIDER_ARN}]}
    calls: list[str] = []

    def _fake_run(cmd: str, **_: object) -> MagicMock:
        calls.append(cmd)
        return _make_run(list_data)

    with patch(f"{_MODULE}.run_and_wait", side_effect=_fake_run):
        arn = provision_oidc_provider(_ACCOUNT_ID)

    assert arn == _EXPECTED_PROVIDER_ARN
    assert not any("create-open-id-connect-provider" in c for c in calls)


def test_provision_oidc_provider_creates_when_missing() -> None:
    list_data = {"OpenIDConnectProviderList": []}
    create_data = {"OpenIDConnectProviderArn": _EXPECTED_PROVIDER_ARN}
    responses = [_make_run(list_data), _make_run(create_data)]
    calls: list[str] = []

    def _fake_run(cmd: str, **_: object) -> MagicMock:
        calls.append(cmd)
        return responses.pop(0)

    with patch(f"{_MODULE}.run_and_wait", side_effect=_fake_run):
        arn = provision_oidc_provider(_ACCOUNT_ID)

    assert arn == _EXPECTED_PROVIDER_ARN
    create_call = next(c for c in calls if "create-open-id-connect-provider" in c)
    assert _GITHUB_ACTIONS_URL in create_call
    assert _GITHUB_THUMBPRINT in create_call


def test_provision_oidc_role_creates_and_attaches_policy() -> None:
    create_data = {"Role": {"Arn": _ROLE_ARN}}
    calls: list[str] = []

    def _fake_run(cmd: str, **_: object) -> MagicMock:
        calls.append(cmd)
        return _make_run(create_data)

    with patch(f"{_MODULE}.run_and_wait", side_effect=_fake_run):
        arn = provision_oidc_role(_ACCOUNT_ID, "myorg", "myrepo", "prod", "my-role", "my-bucket")

    assert arn == _ROLE_ARN
    create_call = next(c for c in calls if "create-role" in c)
    assert "myorg/myrepo" in create_call
    assert "environment:prod" in create_call
    policy_call = next(c for c in calls if "put-role-policy" in c)
    assert "my-bucket" in policy_call


def test_provision_oidc_role_skips_create_when_entity_exists() -> None:
    get_data = {"Role": {"Arn": _ROLE_ARN}}
    calls: list[str] = []

    def _fake_run(cmd: str, **_: object) -> MagicMock:
        calls.append(cmd)
        if "create-role" in cmd:
            raise _make_shell_error(_ENTITY_ALREADY_EXISTS)
        return _make_run(get_data)

    with patch(f"{_MODULE}.run_and_wait", side_effect=_fake_run):
        arn = provision_oidc_role(_ACCOUNT_ID, "myorg", "myrepo", "prod", "my-role", "my-bucket")

    assert arn == _ROLE_ARN
    assert any("get-role" in c for c in calls)
    assert any("put-role-policy" in c for c in calls)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("git@github.com:myorg/myrepo.git", ("myorg", "myrepo")),
        ("https://github.com/myorg/myrepo.git", ("myorg", "myrepo")),
        ("https://github.com/myorg/myrepo", ("myorg", "myrepo")),
    ],
)
def test_parse_github_remote(url: str, expected: tuple[str, str], tmp_path: Path) -> None:
    run = MagicMock()
    run.stdout_one_line = url
    with patch(f"{_MODULE}.run_and_wait", return_value=run):
        assert parse_github_remote(tmp_path) == expected
