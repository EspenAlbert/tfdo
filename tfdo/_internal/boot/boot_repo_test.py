from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from tfdo._internal.boot import boot_repo as _module
from tfdo._internal.boot.boot_repo import CachedModule, TfdoBootInput, boot_repo, select_modules
from tfdo._internal.cache import module_cache as _cache_module
from tfdo._internal.config.config_model import ModuleConstraint
from tfdo._internal.config.provider_hints import ProviderHints
from tfdo._internal.models import InitResult
from tfdo._internal.settings import InteractiveMode, TfDoSettings

_MODULE = _module.__name__
_CACHE_MODULE = _cache_module.__name__


def _settings(tmp_path: Path, interactive: InteractiveMode = InteractiveMode.NEVER) -> TfDoSettings:
    return TfDoSettings.for_testing(tmp_path, work_dir=tmp_path, interactive=interactive)


def _write_hints(tmp_path: Path, content: dict) -> Path:
    path = tmp_path / "provider_hints.yaml"
    path.write_text(yaml.dump(content))
    return path


def test_boot_repo_aborts_if_tfdo_yaml_exists(tmp_path: Path) -> None:
    (tmp_path / "tfdo.yaml").write_text("tf_version: '1.11.0'\n")
    with pytest.raises(ValueError, match="already exists"):
        boot_repo(TfdoBootInput(settings=_settings(tmp_path)))


def test_gitignore_adds_missing_lines_preserves_existing(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("*.pem\n# custom\n")
    with patch(f"{_MODULE}.check_tf_version", return_value="1.11.0"):
        boot_repo(TfdoBootInput(settings=_settings(tmp_path)))

    content = (tmp_path / ".gitignore").read_text()
    assert "*.pem" in content
    assert ".terraform/" in content
    assert ".tfdo/" in content
    assert "*.tfstate" in content


def test_boot_repo_writes_providers_to_yaml(tmp_path: Path) -> None:
    with patch(f"{_MODULE}.check_tf_version", return_value="1.11.0"):
        boot_repo(TfdoBootInput(settings=_settings(tmp_path), providers=["mongodbatlas", "aws"]))

    raw = yaml.safe_load((tmp_path / "tfdo.yaml").read_text())
    assert [p["name"] for p in raw["providers"]] == ["mongodbatlas", "aws"]
    assert raw["tf_version"] == "1.11.0"


def test_create_new_backend_calls_provision_once(tmp_path: Path) -> None:
    with (
        patch(f"{_MODULE}.check_tf_version", return_value="1.11.0"),
        patch(f"{_MODULE}.provision_s3_bucket") as mock_provision,
    ):
        boot_repo(
            TfdoBootInput(
                settings=_settings(tmp_path),
                backend_choice="create-new",
                bucket="my-bucket",
                region="eu-west-1",
            )
        )

    mock_provision.assert_called_once_with("my-bucket", "eu-west-1")
    raw = yaml.safe_load((tmp_path / "tfdo.yaml").read_text())
    assert raw["backend"]["bucket"] == "my-bucket"


def test_create_new_backend_saves_to_user_backends_dir(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with (
        patch(f"{_MODULE}.check_tf_version", return_value="1.11.0"),
        patch(f"{_MODULE}.provision_s3_bucket"),
    ):
        boot_repo(
            TfdoBootInput(
                settings=settings,
                backend_choice="create-new",
                bucket="my-bucket",
                region="eu-west-1",
            )
        )

    backend_file = settings.backends_dirs[0] / "my-bucket.yaml"
    assert backend_file.is_file()
    saved = yaml.safe_load(backend_file.read_text())
    assert saved["bucket"] == "my-bucket"
    assert saved["region"] == "eu-west-1"
    assert saved["type"] == "s3"


def test_saved_backend_appears_in_scan_backend_names(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with (
        patch(f"{_MODULE}.check_tf_version", return_value="1.11.0"),
        patch(f"{_MODULE}.provision_s3_bucket"),
    ):
        boot_repo(
            TfdoBootInput(
                settings=settings,
                backend_choice="create-new",
                bucket="demo-bucket",
                region="us-east-1",
            )
        )

    from tfdo._internal.boot.boot_repo import scan_backend_names

    names = scan_backend_names(settings.backends_dirs)
    assert "demo-bucket" in names


def test_provider_with_no_modules_skips_prompt(tmp_path: Path) -> None:
    hints_path = _write_hints(tmp_path, {"aws": {"source": "hashicorp/aws"}})
    settings = TfDoSettings.for_testing(
        tmp_path, work_dir=tmp_path, interactive=InteractiveMode.ALWAYS, provider_hints_path=hints_path
    )
    with (
        patch(f"{_MODULE}.check_tf_version", return_value="1.11.0"),
        patch(f"{_MODULE}.select_list_multiple_choices") as mock_prompt,
    ):
        result = boot_repo(TfdoBootInput(settings=settings, providers=["aws"]))

    mock_prompt.assert_not_called()
    raw = yaml.safe_load((tmp_path / "tfdo.yaml").read_text())
    assert "modules" not in raw
    assert result.cached_modules == []


def test_modules_written_to_yaml_and_cache_populated(tmp_path: Path) -> None:
    module = ModuleConstraint(source="terraform-mongodbatlas-modules/project")
    with (
        patch(f"{_MODULE}.check_tf_version", return_value="1.11.0"),
        patch(f"{_CACHE_MODULE}.executor") as mock_executor,
    ):
        mock_executor.init.side_effect = _fake_init
        result = boot_repo(TfdoBootInput(settings=_settings(tmp_path), modules=[module]))

    raw = yaml.safe_load((tmp_path / "tfdo.yaml").read_text())
    assert raw["modules"] == [{"source": "terraform-mongodbatlas-modules/project", "constraint": "0.5.0"}]
    assert result.cached_modules == [CachedModule("terraform-mongodbatlas-modules/project", "0.5.0")]


def test_modules_prompt_fires_when_provider_has_modules(tmp_path: Path) -> None:
    hints_path = _write_hints(
        tmp_path,
        {"mongodbatlas": {"modules": [{"source": "tf-modules/project", "alias": "project"}]}},
    )
    settings = TfDoSettings.for_testing(
        tmp_path, work_dir=tmp_path, interactive=InteractiveMode.ALWAYS, provider_hints_path=hints_path
    )
    with (
        patch(f"{_MODULE}.check_tf_version", return_value="1.11.0"),
        patch(f"{_MODULE}.select_list_multiple_choices", return_value=[]) as mock_prompt,
    ):
        boot_repo(TfdoBootInput(settings=settings, providers=["mongodbatlas"]))

    mock_prompt.assert_called_once()
    raw = yaml.safe_load((tmp_path / "tfdo.yaml").read_text())
    assert "modules" not in raw


def _fake_init(input_model):
    modules_dir = input_model.settings.work_dir / ".terraform" / "modules"
    modules_dir.mkdir(parents=True)
    (modules_dir / "modules.json").write_text(
        json.dumps(
            {
                "Modules": [
                    {
                        "Key": "x",
                        "Source": "registry.terraform.io/...",
                        "Version": "0.5.0",
                        "Dir": ".terraform/modules/x",
                    }
                ]
            }
        )
    )
    return InitResult(exit_code=0, attempts_used=1)


def test_select_modules_returns_empty_when_no_hints() -> None:
    registry: dict[str, ProviderHints] = {"aws": ProviderHints()}
    assert select_modules(["aws"], registry) == []


def test_boot_repo_oidc_true_writes_ci_oidc_roles(tmp_path: Path) -> None:
    (tmp_path / "envs" / "dev").mkdir(parents=True)
    _oidc_roles = {"dev": "arn:aws:iam::123:role/tfdo-repo-dev"}
    with (
        patch(f"{_MODULE}.check_tf_version", return_value="1.11.0"),
        patch(f"{_MODULE}._run_oidc_wizard", return_value=_oidc_roles),
    ):
        boot_repo(TfdoBootInput(settings=_settings(tmp_path), oidc=True))

    raw = yaml.safe_load((tmp_path / "tfdo.yaml").read_text())
    assert raw["ci"]["oidc_roles"] == _oidc_roles


def test_boot_repo_oidc_false_does_not_write_ci(tmp_path: Path) -> None:
    with patch(f"{_MODULE}.check_tf_version", return_value="1.11.0"):
        boot_repo(TfdoBootInput(settings=_settings(tmp_path)))

    raw = yaml.safe_load((tmp_path / "tfdo.yaml").read_text())
    assert "ci" not in raw
