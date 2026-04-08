import pytest
from pydantic import ValidationError

from tfdo._internal.config.config_model import (
    DependencyRef,
    HookConfig,
    LocalBackend,
    S3Backend,
    TfDoConfig,
)
from tfdo._internal.config.enums import LifecycleEvent


def test_full_config_from_dict():
    data = {
        "binary": "tofu",
        "tf_version": "1.14",
        "tags_inject": True,
        "tags": {"env": "staging", "team": "infra"},
        "backend": {"type": "s3", "bucket": "my-bucket", "key": "state.tfstate", "region": "us-east-1"},
        "hook_configs": [
            {"name": "fmt-check", "cmd": "terraform fmt -check", "lifecycle_events": ["plan_before"]},
        ],
        "dependencies": [{"ref": "../networking"}],
        "var_files": ["common.tfvars"],
        "run_dir_discovery": "envs/{env}/{app}",
    }
    cfg = TfDoConfig(**data)
    assert cfg.binary == "tofu"
    assert cfg.tags == {"env": "staging", "team": "infra"}
    assert isinstance(cfg.backend, S3Backend)
    assert cfg.hook_configs[0].lifecycle_events == [LifecycleEvent.PLAN_BEFORE]
    assert cfg.dependencies[0].outputs


def test_minimal_config():
    cfg = TfDoConfig()
    assert cfg.binary is None
    assert cfg.tags == {}
    assert cfg.hook_configs == []
    assert cfg.dependencies == []


def test_local_backend_valid():
    b = LocalBackend(path="/tmp/state")
    assert b.path == "/tmp/state"


def test_s3_config_flags():
    b = S3Backend(bucket="b", key="k", region="us-east-1", dynamodb_table="locks", encrypt=True)
    flags = b.config_flags
    assert "-backend-config=bucket=b" in flags
    assert "-backend-config=key=k" in flags
    assert "-backend-config=region=us-east-1" in flags
    assert "-backend-config=dynamodb_table=locks" in flags
    assert "-backend-config=encrypt=true" in flags


def test_s3_config_flags_encrypt_omitted_by_default():
    b = S3Backend(bucket="b", key="k")
    assert not any("encrypt" in f for f in b.config_flags)


def test_local_config_flags():
    b = LocalBackend(path="/tmp/state")
    assert b.config_flags == ["-backend-config=path=/tmp/state"]


def test_hook_config_requires_exactly_one_executor():
    with pytest.raises(ValidationError, match="exactly one"):
        HookConfig(name="bad", lifecycle_events=[LifecycleEvent.ON_OK])
    with pytest.raises(ValidationError, match="exactly one"):
        HookConfig(name="bad", cmd="x", py_locate="y", lifecycle_events=[LifecycleEvent.ON_OK])


def test_hook_config_valid():
    h = HookConfig(name="notify", cmd="echo done", lifecycle_events=[LifecycleEvent.ON_OK, LifecycleEvent.ON_ERROR])
    assert h.timeout_seconds == 30
    assert h.priority == 5000


def test_dependency_ref_defaults():
    d = DependencyRef(ref="../vpc")
    assert d.outputs
