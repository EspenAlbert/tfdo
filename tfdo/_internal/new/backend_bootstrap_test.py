from __future__ import annotations

from pathlib import Path

import yaml

from tfdo._internal.config.config_model import S3Backend
from tfdo._internal.new import backend_bootstrap
from tfdo._internal.new.backend_bootstrap import (
    NewBackendInput,
    new_backend,
    update_tfdo_yaml_backend,
    write_backend_tf_files,
)
from tfdo._internal.settings import TfDoSettings

_MODULE = backend_bootstrap.__name__


def _settings(tmp_path: Path) -> TfDoSettings:
    return TfDoSettings(work_dir=tmp_path)


def test_update_tfdo_yaml_backend_writes_backend_block(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    existing = {"binary": "tofu", "run_dir_discovery": "envs/{env}/{app}"}
    (tmp_path / "tfdo.yaml").write_text(yaml.dump(existing))

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


def test_new_backend_writes_files_without_aws_calls(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "tfdo.yaml").write_text(yaml.dump({"run_dir_discovery": "envs/{env}/{app}", "binary": "tofu"}))
    run_dir = tmp_path / "envs" / "dev" / "cluster"
    run_dir.mkdir(parents=True)
    (run_dir / "main.tf").write_text('resource "null_resource" "x" {}\n')

    result = new_backend(NewBackendInput(settings=_settings(tmp_path), bucket="my-bucket", region="us-east-1"))

    assert result.bucket == "my-bucket"
    assert len(result.backend_tf_files) == 1
    assert (run_dir / "backend.tf").is_file()
