from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import yaml

from tfdo._internal.boot.oidc_bootstrap import OidcWizardResult
from tfdo._internal.config.config_model import CiConfig, S3Backend, TfDoConfig
from tfdo._internal.settings import InteractiveMode, TfDoSettings
from tfdo._internal.sync import sync_github as _module
from tfdo._internal.sync.sync_github import SyncGithubInput, sync_github

_MODULE = _module.__name__


def _settings(tmp_path: Path) -> TfDoSettings:
    return TfDoSettings.for_testing(tmp_path, work_dir=tmp_path, interactive=InteractiveMode.NEVER)


def _s3_config() -> TfDoConfig:
    return TfDoConfig(
        tf_version="1.11.0",
        backend=S3Backend(bucket="state-bucket", key="terraform.tfstate", region="us-east-1"),
    )


def _noop_run_gh(script: str) -> tuple[bool, str]:
    return True, "[]"


def test_sync_github_oidc_triggers_wizard_and_writes_config(tmp_path: Path) -> None:
    config = _s3_config()
    (tmp_path / "envs" / "dev").mkdir(parents=True)
    yaml_path = tmp_path / "tfdo.yaml"
    yaml_path.write_text(yaml.dump(config.model_dump(mode="json", exclude_none=True)))

    oidc_roles = {"dev": "arn:aws:iam::123:role/tfdo-repo-dev"}
    oidc_result = OidcWizardResult(repo_org="my-org", repo_name="my-repo", oidc_roles=oidc_roles)

    with patch(f"{_MODULE}.run_oidc_wizard", return_value=oidc_result) as mock_wizard:
        sync_github(
            SyncGithubInput(
                settings=_settings(tmp_path),
                config=config,
                env_names=["dev"],
                oidc=True,
                run_gh=_noop_run_gh,
                dry_run=True,
            )
        )

    mock_wizard.assert_called_once()
    _, kwargs = mock_wizard.call_args
    assert kwargs["backend_bucket"] == "state-bucket"

    raw = yaml.safe_load(yaml_path.read_text())
    assert raw["ci"]["oidc_roles"] == oidc_roles
    assert raw["ci"]["repo_org"] == "my-org"
    assert raw["ci"]["oidc"]


def test_sync_github_no_oidc_flag_skips_wizard(tmp_path: Path) -> None:
    config = _s3_config()
    (tmp_path / "envs" / "dev").mkdir(parents=True)

    with patch(f"{_MODULE}.run_oidc_wizard") as mock_wizard:
        sync_github(
            SyncGithubInput(
                settings=_settings(tmp_path),
                config=config,
                env_names=["dev"],
                oidc=False,
                run_gh=_noop_run_gh,
                dry_run=True,
            )
        )

    mock_wizard.assert_not_called()


def test_sync_github_existing_oidc_roles_skips_wizard(tmp_path: Path) -> None:
    config = _s3_config()
    config.ci = CiConfig(oidc=True, repo_org="acme", repo_name="infra", oidc_roles={"dev": "arn:existing"})
    (tmp_path / "envs" / "dev").mkdir(parents=True)

    with patch(f"{_MODULE}.run_oidc_wizard") as mock_wizard:
        sync_github(
            SyncGithubInput(
                settings=_settings(tmp_path),
                config=config,
                env_names=["dev"],
                oidc=True,
                run_gh=_noop_run_gh,
                dry_run=True,
            )
        )

    mock_wizard.assert_not_called()


def test_sync_github_oidc_roles_used_for_env_vars(tmp_path: Path) -> None:
    """OIDC wizard result flows into _resolve_env_vars so AWS_ROLE_ARN is available."""
    config = _s3_config()
    config.ci = CiConfig(
        oidc=True,
        repo_org="acme",
        repo_name="infra",
        oidc_roles={"dev": "arn:aws:iam::123:role/tfdo-infra-dev"},
    )
    (tmp_path / "envs" / "dev").mkdir(parents=True)

    result = sync_github(
        SyncGithubInput(
            settings=_settings(tmp_path),
            config=config,
            env_names=["dev"],
            run_gh=_noop_run_gh,
            dry_run=True,
        )
    )

    assert len(result.env_sync_results) == 1
    assert result.env_sync_results[0].env == "dev"


def test_sync_github_no_s3_backend_skips_oidc(tmp_path: Path) -> None:
    config = TfDoConfig(tf_version="1.11.0")
    (tmp_path / "envs" / "dev").mkdir(parents=True)

    with patch(f"{_MODULE}.run_oidc_wizard") as mock_wizard:
        sync_github(
            SyncGithubInput(
                settings=_settings(tmp_path),
                config=config,
                env_names=["dev"],
                oidc=True,
                run_gh=_noop_run_gh,
                dry_run=True,
            )
        )

    mock_wizard.assert_not_called()
