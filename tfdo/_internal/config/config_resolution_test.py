from pathlib import Path
from unittest.mock import patch

from tfdo._internal import settings as settings_mod
from tfdo._internal.config.config_model import HookConfig, TfDoConfig
from tfdo._internal.config.config_resolution import (
    merge_hook_configs,
    merge_tags,
    resolve_config,
    resolve_tflint,
)
from tfdo._internal.config.enums import LifecycleEvent
from tfdo._internal.settings import CheckConfig, InteractiveMode, TfDoSettings, TfDoUserConfig

_patch_user_config_dir = f"{settings_mod.__name__}.{settings_mod.platformdirs.__name__}.user_config_dir"


def _settings(tmp_path: Path) -> TfDoSettings:
    return TfDoSettings.for_testing(tmp_path, work_dir=tmp_path, interactive=InteractiveMode.ALWAYS)


def test_merge_tags_precedence():
    result = merge_tags({"a": "1", "b": "parent"}, {"b": "extra", "c": "3"}, {"b": "local", "d": "4"})
    assert result == {"a": "1", "b": "local", "c": "3", "d": "4"}


def test_merge_hook_configs_sorted():
    h1 = HookConfig(name="z-hook", cmd="echo z", lifecycle_events=[LifecycleEvent.ON_OK], priority=100)
    h2 = HookConfig(name="a-hook", cmd="echo a", lifecycle_events=[LifecycleEvent.ON_OK], priority=100)
    h3 = HookConfig(name="m-hook", cmd="echo m", lifecycle_events=[LifecycleEvent.ON_OK], priority=50)
    result = merge_hook_configs([h1], [h2, h3])
    assert [h.name for h in result] == ["m-hook", "a-hook", "z-hook"]


def test_resolve_config_full(tmp_path: Path):
    parent = TfDoConfig(binary="tofu", tags={"env": "prod"}, tags_inject=True)
    local = TfDoConfig(binary="terraform", tags={"team": "infra"}, var_files=["local.tfvars"])
    result = resolve_config(parent, local, TfDoUserConfig(), _settings(tmp_path))
    assert result.binary == "terraform"
    assert result.tags == {"env": "prod", "team": "infra"}
    assert result.var_files == ["local.tfvars"]
    assert result.tags_inject


def test_resolve_config_standalone(tmp_path: Path):
    local = TfDoConfig(binary="tofu", check=CheckConfig(tflint=True))
    result = resolve_config(None, local, TfDoUserConfig(), _settings(tmp_path))
    assert result.binary == "tofu"
    assert result.check.tflint
    assert result.tags == {}


def test_resolve_config_defaults(tmp_path: Path):
    result = resolve_config(None, None, TfDoUserConfig(), _settings(tmp_path))
    assert result.binary == "terraform"
    assert result.tf_version is None
    assert result.backend is None
    assert not result.tags_inject
    assert not result.check.tflint


def test_resolve_tflint_local_overrides_parent(tmp_path: Path):
    local = TfDoConfig(check=CheckConfig(tflint=True))
    parent = TfDoConfig(check=CheckConfig(tflint=False))
    assert resolve_tflint(None, _settings(tmp_path), local=local, parent=parent)


def test_resolve_tflint_parent_fallback(tmp_path: Path):
    parent = TfDoConfig(check=CheckConfig(tflint=True))
    with patch(_patch_user_config_dir, return_value=str(tmp_path / "config")):
        assert resolve_tflint(None, _settings(tmp_path), parent=parent)


def test_resolve_tflint_cli_wins(tmp_path: Path):
    local = TfDoConfig(check=CheckConfig(tflint=True))
    assert not resolve_tflint(False, _settings(tmp_path), local=local)
