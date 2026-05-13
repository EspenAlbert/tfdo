from __future__ import annotations

from pathlib import Path

from tfdo._internal.models import _TF_PLUGIN_CACHE_DIR_KEY, InitInput
from tfdo._internal.settings import TfDoSettings


def test_init_input_injects_tf_plugin_cache_dir(tmp_path: Path) -> None:
    settings = TfDoSettings.for_testing(tmp_path, work_dir=tmp_path)
    init_input = InitInput(settings=settings)
    assert init_input.env is not None
    assert _TF_PLUGIN_CACHE_DIR_KEY in init_input.env
    assert "tf_plugins" in init_input.env[_TF_PLUGIN_CACHE_DIR_KEY]


def test_init_input_does_not_override_explicit_cache_dir(tmp_path: Path) -> None:
    settings = TfDoSettings.for_testing(tmp_path, work_dir=tmp_path)
    custom = str(tmp_path / "custom_plugins")
    init_input = InitInput(settings=settings, env={_TF_PLUGIN_CACHE_DIR_KEY: custom})
    assert init_input.env is not None
    assert init_input.env[_TF_PLUGIN_CACHE_DIR_KEY] == custom
