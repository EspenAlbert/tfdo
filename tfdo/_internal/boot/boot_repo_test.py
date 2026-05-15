from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import yaml

from tfdo._internal.boot import boot_repo as _module
from tfdo._internal.boot.boot_repo import (
    CachedModule,
    TfdoBootInput,
    boot_repo,
    resolve_repo_identity,
    select_modules,
)
from tfdo._internal.cache import module_cache as _cache_module
from tfdo._internal.cache import provider_version_cache as _pvc_module
from tfdo._internal.config.config_file import load_config
from tfdo._internal.config.config_model import CiConfig, ModuleConstraint, ProviderConstraint, S3Backend, TfDoConfig
from tfdo._internal.config.provider_hints import ProviderHints
from tfdo._internal.git_utils import GitRemote
from tfdo._internal.models import InitResult
from tfdo._internal.settings import InteractiveMode, TfDoSettings

_MODULE = _module.__name__
_CACHE_MODULE = _cache_module.__name__
_PVC_MODULE = _pvc_module.__name__


def _settings(tmp_path: Path, interactive: InteractiveMode = InteractiveMode.NEVER) -> TfDoSettings:
    return TfDoSettings.for_testing(tmp_path, work_dir=tmp_path, interactive=interactive)


def _write_hints(tmp_path: Path, content: dict) -> Path:
    path = tmp_path / "provider_hints.yaml"
    path.write_text(yaml.dump(content))
    return path


def test_boot_rerun_preserves_existing_config(tmp_path: Path) -> None:
    (tmp_path / "tfdo.yaml").write_text(
        yaml.dump({"tf_version": "1.11.0", "backend": {"type": "s3", "bucket": "orig", "key": "terraform.tfstate"}})
    )
    result = boot_repo(TfdoBootInput(settings=_settings(tmp_path)))

    raw = yaml.safe_load((tmp_path / "tfdo.yaml").read_text())
    assert raw["tf_version"] == "1.11.0"
    assert raw["backend"]["bucket"] == "orig"
    assert result.terraform_version == "1.11.0"


def test_boot_backend_type_survives_round_trip(tmp_path: Path) -> None:
    """The 'type' discriminator must be written to tfdo.yaml so load_config can parse it back."""
    with (
        patch(f"{_MODULE}.check_tf_version", return_value="1.11.0"),
        patch(f"{_MODULE}.provision_s3_bucket"),
    ):
        boot_repo(
            TfdoBootInput(
                settings=_settings(tmp_path),
                backend_choice="create-new",
                bucket="round-trip",
                region="us-east-1",
            )
        )

    raw = yaml.safe_load((tmp_path / "tfdo.yaml").read_text())
    assert raw["backend"]["type"] == "s3"

    config = load_config(tmp_path)
    assert config is not None
    assert isinstance(config.backend, S3Backend)
    assert config.backend.bucket == "round-trip"


def test_boot_rerun_applies_explicit_flags(tmp_path: Path) -> None:
    """Re-running boot with explicit providers/backend_choice applies them to existing config."""
    (tmp_path / "tfdo.yaml").write_text(yaml.dump({"tf_version": "1.11.0"}))
    with patch(f"{_MODULE}.provision_s3_bucket") as mock_provision:
        boot_repo(
            TfdoBootInput(
                settings=_settings(tmp_path),
                backend_choice="create-new",
                bucket="my-bucket",
                region="us-east-1",
                providers=[ProviderConstraint(name="aws", source="hashicorp/aws")],
            )
        )

    mock_provision.assert_called_once_with("my-bucket", "us-east-1")
    raw = yaml.safe_load((tmp_path / "tfdo.yaml").read_text())
    assert raw["backend"]["bucket"] == "my-bucket"
    assert [p["name"] for p in raw["providers"]] == ["aws"]
    assert [p["source"] for p in raw["providers"]] == ["hashicorp/aws"]


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
        boot_repo(
            TfdoBootInput(
                settings=_settings(tmp_path),
                providers=[
                    ProviderConstraint(name="mongodbatlas", source="mongodb/mongodbatlas"),
                    ProviderConstraint(name="aws", source="hashicorp/aws"),
                ],
            )
        )

    raw = yaml.safe_load((tmp_path / "tfdo.yaml").read_text())
    assert [p["name"] for p in raw["providers"]] == ["mongodbatlas", "aws"]
    assert [p["source"] for p in raw["providers"]] == ["mongodb/mongodbatlas", "hashicorp/aws"]
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


def _passthrough_resolve(providers, _settings):
    return providers


def test_scaffold_wizard_runs_when_interactive_fresh_repo(tmp_path: Path) -> None:
    hints_path = _write_hints(tmp_path, {"aws": {"source": "hashicorp/aws"}})
    settings = TfDoSettings.for_testing(
        tmp_path, work_dir=tmp_path, interactive=InteractiveMode.ALWAYS, provider_hints_path=hints_path
    )
    with (
        patch(f"{_MODULE}.check_tf_version", return_value="1.11.0"),
        patch(f"{_MODULE}.select_list", return_value="skip") as mock_backend,
        patch(f"{_MODULE}.select_list_multiple_choices", return_value=["aws"]) as mock_providers,
        patch(
            f"{_MODULE}.provider_version_cache.{_pvc_module.resolve_provider_versions.__name__}",
            side_effect=_passthrough_resolve,
        ),
    ):
        result = boot_repo(TfdoBootInput(settings=settings))

    mock_backend.assert_called_once()
    mock_providers.assert_called_once()
    raw = yaml.safe_load((tmp_path / "tfdo.yaml").read_text())
    assert raw["providers"] == [{"name": "aws", "source": "hashicorp/aws"}]
    assert result.backend_choice == "skip"


def test_scaffold_wizard_uses_existing_defaults(tmp_path: Path) -> None:
    """When re-running interactively on existing config, wizard pre-selects current providers."""
    hints_path = _write_hints(tmp_path, {"aws": {"source": "hashicorp/aws"}, "mongodbatlas": {}})
    settings = TfDoSettings.for_testing(
        tmp_path, work_dir=tmp_path, interactive=InteractiveMode.ALWAYS, provider_hints_path=hints_path
    )
    (tmp_path / "tfdo.yaml").write_text(yaml.dump({"tf_version": "1.11.0", "providers": [{"name": "aws"}]}))
    with (
        patch(f"{_MODULE}.select_list", return_value="skip") as mock_backend,
        patch(f"{_MODULE}.select_list_multiple_choices", return_value=["aws", "mongodbatlas"]) as mock_providers,
    ):
        boot_repo(TfdoBootInput(settings=settings))

    mock_backend.assert_called_once()
    provider_choices = mock_providers.call_args[0][1]
    checked_names = {c.name for c in provider_choices if c.checked}
    assert checked_names == {"aws"}


def test_scaffold_wizard_skipped_when_not_interactive(tmp_path: Path) -> None:
    with (
        patch(f"{_MODULE}.check_tf_version", return_value="1.11.0"),
        patch(f"{_MODULE}.select_list") as mock_backend,
    ):
        boot_repo(TfdoBootInput(settings=_settings(tmp_path)))

    mock_backend.assert_not_called()


def test_scaffold_wizard_skipped_when_fields_pre_populated(tmp_path: Path) -> None:
    with (
        patch(f"{_MODULE}.check_tf_version", return_value="1.11.0"),
        patch(f"{_MODULE}.select_list") as mock_backend,
    ):
        boot_repo(TfdoBootInput(settings=_settings(tmp_path), providers=[ProviderConstraint(name="aws")]))

    mock_backend.assert_not_called()


def test_select_modules_returns_empty_when_no_hints() -> None:
    registry: dict[str, ProviderHints] = {"aws": ProviderHints()}
    assert select_modules(["aws"], registry) == []


def test_boot_pins_provider_versions(tmp_path: Path) -> None:
    providers = [
        ProviderConstraint(name="aws", source="hashicorp/aws"),
        ProviderConstraint(name="mongodbatlas", source="mongodb/mongodbatlas"),
    ]
    pinned = [
        ProviderConstraint(name="aws", source="hashicorp/aws", constraint="5.82.0"),
        ProviderConstraint(name="mongodbatlas", source="mongodb/mongodbatlas", constraint="1.23.0"),
    ]
    with (
        patch(f"{_MODULE}.check_tf_version", return_value="1.11.0"),
        patch(f"{_PVC_MODULE}.resolve_provider_versions", return_value=pinned),
    ):
        boot_repo(TfdoBootInput(settings=_settings(tmp_path), providers=providers))

    raw = yaml.safe_load((tmp_path / "tfdo.yaml").read_text())
    constraints = {p["name"]: p.get("constraint") for p in raw["providers"]}
    assert constraints == {"aws": "5.82.0", "mongodbatlas": "1.23.0"}


def test_resolve_repo_identity_from_git_remote_non_interactive(tmp_path: Path) -> None:
    config = TfDoConfig(tf_version="1.11.0")
    settings = _settings(tmp_path, interactive=InteractiveMode.NEVER)
    remote = GitRemote(org="acme", repo="infra")
    with patch(f"{_MODULE}.parse_git_remote", return_value=remote):
        resolve_repo_identity(settings, config)

    assert config.ci is not None
    assert config.ci.repo_org == "acme"
    assert config.ci.repo_name == "infra"


def test_resolve_repo_identity_no_git_remote_non_interactive(tmp_path: Path) -> None:
    config = TfDoConfig(tf_version="1.11.0")
    settings = _settings(tmp_path, interactive=InteractiveMode.NEVER)
    with patch(f"{_MODULE}.parse_git_remote", return_value=None):
        resolve_repo_identity(settings, config)

    assert config.ci is None


def test_resolve_repo_identity_interactive_prompts(tmp_path: Path) -> None:
    config = TfDoConfig(tf_version="1.11.0")
    settings = _settings(tmp_path, interactive=InteractiveMode.ALWAYS)
    with (
        patch(f"{_MODULE}.parse_git_remote", return_value=GitRemote(org="default-org", repo="default-repo")),
        patch(f"{_MODULE}.text", side_effect=["my-org", "my-repo"]) as mock_text,
    ):
        resolve_repo_identity(settings, config)

    assert config.ci is not None
    assert config.ci.repo_org == "my-org"
    assert config.ci.repo_name == "my-repo"
    assert mock_text.call_count == 2
    assert mock_text.call_args_list[0].kwargs["default"] == "default-org"
    assert mock_text.call_args_list[1].kwargs["default"] == "default-repo"


def test_resolve_repo_identity_skips_when_already_set(tmp_path: Path) -> None:
    config = TfDoConfig(tf_version="1.11.0", ci=CiConfig(repo_org="existing-org", repo_name="existing-repo"))
    settings = _settings(tmp_path, interactive=InteractiveMode.ALWAYS)
    with patch(f"{_MODULE}.parse_git_remote") as mock_remote:
        resolve_repo_identity(settings, config)

    mock_remote.assert_not_called()
    assert config.ci is not None
    assert config.ci.repo_org == "existing-org"
    assert config.ci.repo_name == "existing-repo"


def test_boot_writes_repo_identity_without_oidc(tmp_path: Path) -> None:
    remote = GitRemote(org="my-org", repo="my-repo")
    with (
        patch(f"{_MODULE}.check_tf_version", return_value="1.11.0"),
        patch(f"{_MODULE}.parse_git_remote", return_value=remote),
    ):
        boot_repo(TfdoBootInput(settings=_settings(tmp_path)))

    raw = yaml.safe_load((tmp_path / "tfdo.yaml").read_text())
    assert raw["ci"]["repo_org"] == "my-org"
    assert raw["ci"]["repo_name"] == "my-repo"
    assert not raw["ci"]["oidc"]
