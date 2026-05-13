from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from tfdo._internal.init import init_repo as _module
from tfdo._internal.init.init_repo import TfdoInitInput, init_repo
from tfdo._internal.settings import TfDoSettings

_MODULE = _module.__name__


def _settings(tmp_path: Path) -> TfDoSettings:
    return TfDoSettings.for_testing(tmp_path, work_dir=tmp_path)


def test_init_repo_aborts_if_tfdo_yaml_exists(tmp_path: Path) -> None:
    (tmp_path / "tfdo.yaml").write_text("tf_version: '1.11.0'\n")
    with pytest.raises(ValueError, match="already exists"):
        init_repo(TfdoInitInput(settings=_settings(tmp_path)))


def test_gitignore_adds_missing_lines_preserves_existing(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("*.pem\n# custom\n")
    with patch(f"{_MODULE}.check_tf_version", return_value="1.11.0"):
        init_repo(TfdoInitInput(settings=_settings(tmp_path)))

    content = (tmp_path / ".gitignore").read_text()
    assert "*.pem" in content
    assert ".terraform/" in content
    assert ".tfdo/" in content
    assert "*.tfstate" in content


def test_init_repo_writes_providers_to_yaml(tmp_path: Path) -> None:
    with patch(f"{_MODULE}.check_tf_version", return_value="1.11.0"):
        init_repo(TfdoInitInput(settings=_settings(tmp_path), providers=["mongodbatlas", "aws"]))

    raw = yaml.safe_load((tmp_path / "tfdo.yaml").read_text())
    assert [p["name"] for p in raw["providers"]] == ["mongodbatlas", "aws"]
    assert raw["tf_version"] == "1.11.0"


def test_create_new_backend_calls_provision_once(tmp_path: Path) -> None:
    with (
        patch(f"{_MODULE}.check_tf_version", return_value="1.11.0"),
        patch(f"{_MODULE}.provision_s3_bucket") as mock_provision,
    ):
        init_repo(
            TfdoInitInput(
                settings=_settings(tmp_path),
                backend_choice="create-new",
                bucket="my-bucket",
                region="eu-west-1",
            )
        )

    mock_provision.assert_called_once_with("my-bucket", "eu-west-1")
    raw = yaml.safe_load((tmp_path / "tfdo.yaml").read_text())
    assert raw["backend"]["bucket"] == "my-bucket"
