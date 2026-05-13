from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tfdo._internal.init import s3_bootstrap
from tfdo._internal.init.s3_bootstrap import check_tf_version, provision_s3_bucket

_MODULE = s3_bootstrap.__name__


def _mock_version_run(version_data: dict) -> MagicMock:
    run = MagicMock()
    run.parse_output.return_value = version_data
    return run


def test_check_tf_version_passes_for_1_11() -> None:
    with patch(f"{_MODULE}.run_and_wait", return_value=_mock_version_run({"terraform_version": "1.11.0"})):
        version = check_tf_version("terraform")
    assert version == "1.11.0"


def test_check_tf_version_raises_for_old_version() -> None:
    with patch(f"{_MODULE}.run_and_wait", return_value=_mock_version_run({"terraform_version": "1.9.3"})):
        with pytest.raises(ValueError, match="too old"):
            check_tf_version("terraform")


def test_provision_s3_bucket_issues_four_commands() -> None:
    calls: list[str] = []

    def _fake_run(cmd: str, **_: object) -> MagicMock:
        calls.append(cmd)
        return MagicMock()

    with patch(f"{_MODULE}.run_and_wait", side_effect=_fake_run):
        provision_s3_bucket("my-bucket", "eu-west-1")

    assert any("create-bucket" in c for c in calls)
    assert any("LocationConstraint=eu-west-1" in c for c in calls)
    assert any("put-bucket-versioning" in c for c in calls)
    assert any("put-bucket-encryption" in c for c in calls)
    assert any("put-public-access-block" in c for c in calls)


def test_provision_s3_bucket_skips_location_constraint_for_us_east_1() -> None:
    calls: list[str] = []

    def _fake_run(cmd: str, **_: object) -> MagicMock:
        calls.append(cmd)
        return MagicMock()

    with patch(f"{_MODULE}.run_and_wait", side_effect=_fake_run):
        provision_s3_bucket("my-bucket", "us-east-1")

    create_call = next(c for c in calls if "create-bucket" in c)
    assert "LocationConstraint" not in create_call
