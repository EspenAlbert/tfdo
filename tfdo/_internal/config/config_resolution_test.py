from pathlib import Path
from unittest.mock import patch

from tfdo._internal import settings as settings_mod
from tfdo._internal.config.config_file import ConfigLayer
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


def _layer(config: TfDoConfig, name: str = "tfdo.yaml") -> ConfigLayer:
    return ConfigLayer(config, Path(name))


def test_merge_tags_most_specific_wins():
    result = merge_tags(
        [{"env": "local"}, {"env": "mid", "tier": "mid"}, {"env": "root", "org": "acme"}],
        {"extra": "yes"},
    )
    assert result == {"org": "acme", "tier": "mid", "env": "local", "extra": "yes"}


def test_merge_hook_configs_sorted():
    h1 = HookConfig(name="z-hook", cmd="echo z", lifecycle_events=[LifecycleEvent.ON_OK], priority=100)
    h2 = HookConfig(name="a-hook", cmd="echo a", lifecycle_events=[LifecycleEvent.ON_OK], priority=100)
    h3 = HookConfig(name="m-hook", cmd="echo m", lifecycle_events=[LifecycleEvent.ON_OK], priority=50)
    result = merge_hook_configs([[h1], [h2, h3]])
    assert [h.name for h in result] == ["m-hook", "a-hook", "z-hook"]


def test_resolve_config_two_layers(tmp_path: Path):
    layers = [
        _layer(TfDoConfig(binary="terraform", tags={"team": "infra"}, var_files=["local.tfvars"])),
        _layer(TfDoConfig(binary="tofu", tags={"env": "prod"}, tags_inject=True)),
    ]
    result = resolve_config(layers, TfDoUserConfig(), _settings(tmp_path))
    assert result.binary == "terraform"
    assert result.tags == {"env": "prod", "team": "infra"}
    assert result.var_files == ["local.tfvars"]
    assert result.tags_inject


def test_resolve_config_three_layers(tmp_path: Path):
    layers = [
        _layer(TfDoConfig(tags={"env": "staging"})),
        _layer(TfDoConfig(tags={"tier": "mid"}, binary="tofu")),
        _layer(TfDoConfig(tags={"env": "root", "org": "acme"}, tags_inject=True)),
    ]
    result = resolve_config(layers, TfDoUserConfig(), _settings(tmp_path))
    assert result.binary == "tofu"
    assert result.tags == {"org": "acme", "tier": "mid", "env": "staging"}
    assert result.tags_inject


def test_resolve_config_standalone(tmp_path: Path):
    layers = [_layer(TfDoConfig(binary="tofu", check=CheckConfig(tflint=True)))]
    result = resolve_config(layers, TfDoUserConfig(), _settings(tmp_path))
    assert result.binary == "tofu"
    assert result.check.tflint
    assert result.tags == {}


def test_resolve_config_defaults(tmp_path: Path):
    result = resolve_config([], TfDoUserConfig(), _settings(tmp_path))
    assert result.binary == "terraform"
    assert result.tf_version is None
    assert not result.tags_inject
    assert not result.check.tflint


def test_resolve_tflint_most_specific_wins(tmp_path: Path):
    layers = [
        _layer(TfDoConfig(check=CheckConfig(tflint=True))),
        _layer(TfDoConfig(check=CheckConfig(tflint=False))),
    ]
    assert resolve_tflint(None, _settings(tmp_path), layers=layers)


def test_resolve_tflint_ancestor_fallback(tmp_path: Path):
    layers = [_layer(TfDoConfig()), _layer(TfDoConfig(check=CheckConfig(tflint=True)))]
    with patch(_patch_user_config_dir, return_value=str(tmp_path / "config")):
        assert resolve_tflint(None, _settings(tmp_path), layers=layers)


def test_resolve_tflint_cli_wins(tmp_path: Path):
    layers = [_layer(TfDoConfig(check=CheckConfig(tflint=True)))]
    assert not resolve_tflint(False, _settings(tmp_path), layers=layers)
