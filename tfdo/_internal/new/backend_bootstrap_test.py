from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from tfdo._internal.config.config_model import S3Backend
from tfdo._internal.new import backend_bootstrap
from tfdo._internal.new.backend_bootstrap import (
    NewBackendInput,
    check_tf_version,
    new_backend,
    provision_s3_bucket,
    update_tfdo_yaml_backend,
    write_backend_tf_files,
)
from tfdo._internal.settings import TfDoSettings

_MODULE = backend_bootstrap.__name__


def _mock_version_run(version_data: dict) -> MagicMock:
    run = MagicMock()
    run.parse_output.return_value = version_data
    return run


def _mock_run() -> MagicMock:
    return MagicMock()


def _settings(tmp_path: Path) -> TfDoSettings:
    return TfDoSettings(work_dir=tmp_path)


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
        return _mock_run()

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
        return _mock_run()

    with patch(f"{_MODULE}.run_and_wait", side_effect=_fake_run):
        provision_s3_bucket("my-bucket", "us-east-1")

    create_call = next(c for c in calls if "create-bucket" in c)
    assert "LocationConstraint" not in create_call


def test_update_tfdo_yaml_backend_writes_backend_block(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    existing = {"binary": "tofu", "run_dir_discovery": "envs/{env}/{app}"}
    (tmp_path / "tfdo.yaml").write_text(yaml.dump(existing))

    from tfdo._internal.config.config_model import S3Backend

    backend = S3Backend(bucket="my-bucket", key="{path}/terraform.tfstate", region="us-east-1", encrypt=True)
    update_tfdo_yaml_backend(tmp_path, backend)

    data = yaml.safe_load((tmp_path / "tfdo.yaml").read_text())
    assert data["binary"] == "tofu"
    assert data["backend"]["bucket"] == "my-bucket"
    assert data["backend"]["use_lockfile"]
    assert data["backend"]["type"] == "s3"


def test_write_backend_tf_files_creates_backend_tf(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "tfdo.yaml").write_text(yaml.dump({"run_dir_discovery": "envs/{env}/{app}", "binary": "tofu"}))
    run_dir = tmp_path / "envs" / "dev" / "cluster"
    run_dir.mkdir(parents=True)
    (run_dir / "main.tf").write_text('resource "null_resource" "x" {}\n')

    backend = S3Backend(bucket="my-bucket", key="{path}/terraform.tfstate", region="us-east-1", encrypt=True)
    files = write_backend_tf_files(tmp_path, backend)

    assert len(files) == 1
    content = (run_dir / "backend.tf").read_text()
    assert 'backend "s3"' in content
    assert "envs/dev/cluster/terraform.tfstate" in content
    assert "my-bucket" in content


def test_new_backend_dry_run_skips_aws_but_writes_files(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "tfdo.yaml").write_text(yaml.dump({"run_dir_discovery": "envs/{env}/{app}", "binary": "tofu"}))
    run_dir = tmp_path / "envs" / "dev" / "cluster"
    run_dir.mkdir(parents=True)
    (run_dir / "main.tf").write_text('resource "null_resource" "x" {}\n')

    with patch(f"{_MODULE}.run_and_wait", return_value=_mock_version_run({"tofu_version": "1.11.0"})):
        result = new_backend(
            NewBackendInput(
                settings=_settings(tmp_path),
                bucket="my-bucket",
                region="us-east-1",
                dry_run=True,
            )
        )

    assert result.bucket == "my-bucket"
    assert len(result.backend_tf_files) == 1
    assert (run_dir / "backend.tf").is_file()
