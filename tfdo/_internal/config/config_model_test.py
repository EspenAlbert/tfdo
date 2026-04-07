import pytest
from pydantic import ValidationError

from tfdo._internal.config.config_model import (
    BackendDefaults,
    DependencyRef,
    HookConfig,
    TfDoConfig,
)
from tfdo._internal.config.enums import BackendType, LifecycleEvent


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
    assert cfg.backend is not None
    assert cfg.backend.type == BackendType.S3
    assert cfg.hook_configs[0].lifecycle_events == [LifecycleEvent.PLAN_BEFORE]
    assert cfg.dependencies[0].outputs


def test_minimal_config():
    cfg = TfDoConfig()
    assert cfg.binary is None
    assert cfg.tags == {}
    assert cfg.hook_configs == []
    assert cfg.dependencies == []


def test_backend_s3_requires_bucket_and_key():
    with pytest.raises(ValidationError, match="bucket"):
        BackendDefaults(type=BackendType.S3)


def test_backend_local_requires_path():
    with pytest.raises(ValidationError, match="path"):
        BackendDefaults(type=BackendType.LOCAL, bucket="x", key="y")


def test_backend_local_valid():
    b = BackendDefaults(type=BackendType.LOCAL, path="/tmp/state")
    assert b.path == "/tmp/state"


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
