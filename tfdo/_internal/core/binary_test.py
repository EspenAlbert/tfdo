from pathlib import Path
from shutil import which
from unittest.mock import patch

import pytest

from tfdo._internal.core.binary import MiseMissingError, resolve_binary
from tfdo._internal.settings import InteractiveMode, TfDoSettings

module_name = resolve_binary.__module__
_patch_which = f"{module_name}.{which.__name__}"


def _make_settings(tmp_path: Path, binary: str = "terraform", tf_version: str | None = None) -> TfDoSettings:
    return TfDoSettings.for_testing(
        tmp_path, work_dir=tmp_path, interactive=InteractiveMode.ALWAYS, binary=binary, tf_version=tf_version
    )


def test_resolve_binary_no_version(tmp_path: Path):
    settings = _make_settings(tmp_path)
    assert resolve_binary(settings) == "terraform"


def test_resolve_binary_with_version(tmp_path: Path):
    settings = _make_settings(tmp_path, tf_version="1.14.0")
    with patch(_patch_which, return_value="/usr/local/bin/mise"):
        assert resolve_binary(settings) == "mise x terraform@1.14.0 -- terraform"


def test_resolve_binary_tofu_with_version(tmp_path: Path):
    settings = _make_settings(tmp_path, binary="tofu", tf_version="1.8.0")
    with patch(_patch_which, return_value="/usr/local/bin/mise"):
        assert resolve_binary(settings) == "mise x tofu@1.8.0 -- tofu"


def test_resolve_binary_mise_missing(tmp_path: Path):
    settings = _make_settings(tmp_path, tf_version="1.14.0")
    with patch(_patch_which, return_value=None), pytest.raises(MiseMissingError, match="mise"):
        resolve_binary(settings)
