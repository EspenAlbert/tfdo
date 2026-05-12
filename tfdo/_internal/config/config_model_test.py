import pytest
from pydantic import ValidationError

from tfdo._internal.config.config_model import (
    DependencyRef,
    HookConfig,
    LocalBackend,
    ProviderConstraint,
    S3Backend,
    TfDoConfig,
    merge_providers,
)
from tfdo._internal.config.enums import LifecycleEvent


def test_full_config_from_dict():
    data = {
        "binary": "tofu",
        "tf_version": "1.14",
        "tags_inject": "always",
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


def test_s3_use_lockfile_defaults_true_when_no_dynamodb_table():
    b = S3Backend(bucket="b", key="k")
    assert b.use_lockfile is True
    assert "-backend-config=use_lockfile=true" in b.config_flags


def test_s3_use_lockfile_false_when_dynamodb_table_set():
    b = S3Backend(bucket="b", key="k", dynamodb_table="locks")
    assert not b.use_lockfile
    assert not any("use_lockfile" in f for f in b.config_flags)


def test_s3_use_lockfile_explicit_true_overrides_dynamodb_table():
    b = S3Backend(bucket="b", key="k", dynamodb_table="locks", use_lockfile=True)
    assert b.use_lockfile is True


def test_s3_hcl_config_includes_set_fields():
    b = S3Backend(bucket="my-bucket", key="state/terraform.tfstate", region="us-east-1", encrypt=True)
    cfg = b.hcl_config
    assert cfg["bucket"] == '"my-bucket"'
    assert cfg["region"] == '"us-east-1"'
    assert cfg["encrypt"] is True
    assert cfg["use_lockfile"] is True


def test_s3_hcl_config_omits_use_lockfile_when_dynamodb_table_set():
    b = S3Backend(bucket="b", key="k", dynamodb_table="locks")
    cfg = b.hcl_config
    assert "region" not in cfg
    assert "encrypt" not in cfg
    assert "use_lockfile" not in cfg


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


def _cfg(*providers: tuple[str, str | None]) -> TfDoConfig:
    return TfDoConfig(providers=[ProviderConstraint(name=n, constraint=c) for n, c in providers])


def test_merge_providers_dev_inherits_root():
    root = _cfg(("mongodbatlas", "~> 2.0"))
    dev = TfDoConfig()
    result = merge_providers([root], dev)
    assert len(result) == 1
    assert result[0].name == "mongodbatlas"
    assert result[0].constraint == "~> 2.0"


def test_merge_providers_prod_overrides_constraint():
    root = _cfg(("mongodbatlas", "~> 2.0"))
    prod = _cfg(("mongodbatlas", "~> 2.10"))
    result = merge_providers([root], prod)
    assert len(result) == 1
    assert result[0].constraint == "~> 2.10"


def test_merge_providers_child_adds_new_name():
    root = _cfg(("mongodbatlas", "~> 2.0"))
    child = _cfg(("random", None))
    result = merge_providers([root], child)
    names = {p.name for p in result}
    assert names == {"mongodbatlas", "random"}


def test_merge_providers_child_clears_constraint():
    root = _cfg(("mongodbatlas", "~> 2.0"))
    child = _cfg(("mongodbatlas", None))
    result = merge_providers([root], child)
    assert len(result) == 1
    assert result[0].name == "mongodbatlas"
    assert result[0].constraint is None


def test_provider_constraint_round_trip():
    cfg = TfDoConfig(providers=[ProviderConstraint(name="mongodbatlas", constraint="~> 2.1")])
    dumped = cfg.model_dump()
    reloaded = TfDoConfig(**dumped)
    assert reloaded.providers[0].name == "mongodbatlas"
    assert reloaded.providers[0].constraint == "~> 2.1"
