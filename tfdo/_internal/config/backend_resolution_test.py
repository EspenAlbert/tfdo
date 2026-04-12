from pathlib import Path

import pytest

from tfdo._internal.config.backend_resolution import resolve_init_backend_args, resolve_placeholders
from tfdo._internal.config.config_model import LocalBackend, S3Backend
from tfdo._internal.run.run_context import RunDirContext

_CTX = RunDirContext(
    name="compute",
    path="envs/staging/compute",
    repo_owner="AcmeCorp",
    repo_name="infra",
    tags={"env": "staging", "team": "platform"},
)


def test_resolve_builtins_and_tags():
    template = "{repo_owner}/{repo_name}/{path}/{name}-{tags.env}-{team}"
    assert resolve_placeholders(template, _CTX) == "AcmeCorp/infra/envs/staging/compute/compute-staging-platform"


def test_resolve_unresolved_raises_with_suggestions():
    with pytest.raises(ValueError, match="Add the missing key to tags") as exc_info:
        resolve_placeholders("{missing}", _CTX)
    msg = str(exc_info.value)
    assert "Available:" in msg
    assert "name" in msg
    assert "tags.env" in msg


def test_builtins_win_over_tags():
    ctx = RunDirContext(name="x", path="y", repo_owner="o", repo_name="r", tags={"name": "from-tag"})
    assert resolve_placeholders("{name}", ctx) == "x"


def test_s3_backend_args():
    backend = S3Backend(bucket="my-bucket", key="{repo_name}/{path}/terraform.tfstate", region="us-east-1")
    args = resolve_init_backend_args(backend, _CTX)
    assert "-backend-config=bucket=my-bucket" in args
    assert "-backend-config=key=infra/envs/staging/compute/terraform.tfstate" in args
    assert "-backend-config=region=us-east-1" in args
    assert not any("encrypt" in a for a in args)
    assert not any("dynamodb_table" in a for a in args)


def test_s3_backend_with_dynamodb():
    backend = S3Backend(bucket="b", key="k", dynamodb_table="locks-{tags.env}")
    args = resolve_init_backend_args(backend, _CTX)
    assert "-backend-config=dynamodb_table=locks-staging" in args


def test_local_backend_creates_parent_dir(tmp_path: Path):
    state_file = tmp_path / "state" / "compute" / "terraform.tfstate"
    backend = LocalBackend(path=str(state_file))
    args = resolve_init_backend_args(backend, _CTX)
    assert args == [f"-backend-config=path={state_file}"]
    assert state_file.parent.is_dir()
    assert not state_file.exists()


def test_none_backend_returns_empty():
    assert resolve_init_backend_args(None, _CTX) == []
