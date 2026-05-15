from pathlib import Path

import pytest

from tfdo._internal.config.backend_resolution import (
    ensure_backend_tf,
    has_backend_drift,
    resolve_init_backend_args,
    resolve_placeholders,
)
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
    with pytest.raises(ValueError, match="unresolved placeholders") as exc_info:
        resolve_placeholders("{missing}", _CTX)
    msg = str(exc_info.value)
    assert "Populated:" in msg
    assert "name" in msg
    assert "tags.env" in msg


def test_empty_builtin_raises():
    ctx = RunDirContext(name="compute", path="envs/dev/compute", repo_owner="", repo_name="")
    with pytest.raises(ValueError, match="Empty builtins") as exc_info:
        resolve_placeholders("{repo_owner}/{repo_name}/{path}/terraform.tfstate", ctx)
    msg = str(exc_info.value)
    assert "repo_owner" in msg
    assert "repo_name" in msg


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


def test_ensure_backend_tf_creates_file(tmp_path: Path):
    run_dir = tmp_path / "envs" / "staging" / "compute"
    run_dir.mkdir(parents=True)
    backend = S3Backend(bucket="my-bucket", key="{repo_owner}/{path}/terraform.tfstate", region="us-east-1")
    changed = ensure_backend_tf(run_dir, backend, _CTX)
    assert changed
    content = (run_dir / "backend.tf").read_text()
    assert "AcmeCorp/envs/staging/compute/terraform.tfstate" in content
    assert "my-bucket" in content


def test_ensure_backend_tf_detects_drift(tmp_path: Path):
    run_dir = tmp_path / "envs" / "staging" / "compute"
    run_dir.mkdir(parents=True)
    backend = S3Backend(bucket="my-bucket", key="{repo_owner}/{path}/terraform.tfstate", region="us-east-1")
    (run_dir / "backend.tf").write_text(
        'terraform {\n  backend "s3" {\n    bucket = "my-bucket"\n    key    = "AcmeCorp/envs/dev/compute/terraform.tfstate"\n    region = "us-east-1"\n  }\n}\n'
    )

    changed = ensure_backend_tf(run_dir, backend, _CTX)
    assert changed
    content = (run_dir / "backend.tf").read_text()
    assert "AcmeCorp/envs/staging/compute/terraform.tfstate" in content


def test_ensure_backend_tf_no_change_returns_false(tmp_path: Path):
    run_dir = tmp_path / "envs" / "staging" / "compute"
    run_dir.mkdir(parents=True)
    backend = S3Backend(bucket="my-bucket", key="{repo_owner}/{path}/terraform.tfstate", region="us-east-1")
    ensure_backend_tf(run_dir, backend, _CTX)
    changed = ensure_backend_tf(run_dir, backend, _CTX)
    assert not changed


def test_has_backend_drift_detects_stale_key(tmp_path: Path):
    run_dir = tmp_path / "envs" / "staging" / "compute"
    run_dir.mkdir(parents=True)
    backend = S3Backend(bucket="my-bucket", key="{repo_owner}/{path}/terraform.tfstate", region="us-east-1")
    (run_dir / "backend.tf").write_text(
        'terraform {\n  backend "s3" {\n    bucket = "my-bucket"\n    key    = "wrong/key"\n    region = "us-east-1"\n  }\n}\n'
    )
    assert has_backend_drift(run_dir, backend, _CTX)


def test_has_backend_drift_returns_false_when_in_sync(tmp_path: Path):
    run_dir = tmp_path / "envs" / "staging" / "compute"
    run_dir.mkdir(parents=True)
    backend = S3Backend(bucket="my-bucket", key="{repo_owner}/{path}/terraform.tfstate", region="us-east-1")
    ensure_backend_tf(run_dir, backend, _CTX)
    assert not has_backend_drift(run_dir, backend, _CTX)


_S3_BACKEND_HCL_STALE_KEY = (
    "terraform {\n"
    '  backend "s3" {\n'
    '    bucket = "my-bucket"\n'
    '    key    = "AcmeCorp/envs/dev/compute/terraform.tfstate"\n'
    '    region = "us-east-1"\n'
    "  }\n"
    "}\n"
)


def test_ensure_backend_tf_finds_named_tf_file(tmp_path: Path):
    run_dir = tmp_path / "envs" / "staging" / "compute"
    run_dir.mkdir(parents=True)
    (run_dir / "remote_backend.tf").write_text(_S3_BACKEND_HCL_STALE_KEY)

    backend = S3Backend(bucket="my-bucket", key="{repo_owner}/{path}/terraform.tfstate", region="us-east-1")

    changed = ensure_backend_tf(run_dir, backend, _CTX)
    assert changed
    remote = run_dir / "remote_backend.tf"
    assert remote.is_file()
    assert "AcmeCorp/envs/staging/compute/terraform.tfstate" in remote.read_text()


def test_ensure_backend_tf_splices_into_existing_terraform_file(tmp_path: Path):
    run_dir = tmp_path / "leaf"
    run_dir.mkdir(parents=True)
    tf_path = run_dir / "versions.tf"
    tf_path.write_text('terraform {\n  required_version = ">= 1.7"\n}\n')

    backend = S3Backend(bucket="buck", key="{repo_name}/terraform.tfstate", region="eu-west-1")

    changed = ensure_backend_tf(run_dir, backend, _CTX)
    assert changed
    out = tf_path.read_text()
    assert 'backend "s3"' in out
    assert "buck" in out
    assert "infra/terraform.tfstate" in out


def test_exclusive_backend_conflict_raises(tmp_path: Path):
    run_dir = tmp_path / "dup"
    run_dir.mkdir(parents=True)
    (run_dir / "one.tf").write_text(_S3_BACKEND_HCL_STALE_KEY)
    (run_dir / "two.tf").write_text(_S3_BACKEND_HCL_STALE_KEY)
    backend = S3Backend(bucket="my-bucket", key="{path}/terraform.tfstate", region="us-east-1")

    with pytest.raises(ValueError, match=r"multiple terraform backend"):
        ensure_backend_tf(run_dir, backend, _CTX)
