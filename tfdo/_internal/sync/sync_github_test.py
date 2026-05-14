from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from tfdo._internal.config.config_model import TFDO_DEFAULT_INSTALL, CiConfig, ProviderConstraint, S3Backend, TfDoConfig
from tfdo._internal.config.provider_hints import AuthBundle, ProviderHints, VariableMapping
from tfdo._internal.settings import TfDoSettings
from tfdo._internal.sync.sync_github import (
    ACTION_AWS_CREDS,
    ACTION_SETUP_UV,
    SyncGithubInput,
    _resolve_env_vars,
    collect_requirements,
    resolve_secret_values,
    sync_github,
)

_ATLAS_HINTS = ProviderHints(
    auth_bundles=[
        AuthBundle(name="api_key", secrets=["MONGODB_ATLAS_PUBLIC_KEY", "MONGODB_ATLAS_PRIVATE_KEY"]),
        AuthBundle(name="service_account", secrets=["MONGODB_ATLAS_CLIENT_ID", "MONGODB_ATLAS_CLIENT_SECRET"]),
    ],
    auth_variables=[VariableMapping(env="MONGODB_ATLAS_ORG_ID", tf_var="org_id")],
)


def _settings(tmp_path: Path) -> TfDoSettings:
    return TfDoSettings(work_dir=tmp_path)


def _make_envs(tmp_path: Path, names: list[str]) -> None:
    for name in names:
        (tmp_path / "envs" / name).mkdir(parents=True)


def _config_with_s3() -> TfDoConfig:
    return TfDoConfig(
        providers=[ProviderConstraint(name="mongodbatlas")],
        backend=S3Backend(bucket="my-bucket", key="state.tfstate", region="us-east-1"),
    )


def _gh_call_recorder() -> tuple[list[str], Callable[[str], tuple[bool, str]]]:
    calls: list[str] = []

    def recorder(script: str) -> tuple[bool, str]:
        calls.append(script)
        return True, ""

    return calls, recorder


_ATLAS_ENV_VARS = {
    "MONGODB_ATLAS_PUBLIC_KEY": "p",
    "MONGODB_ATLAS_PRIVATE_KEY": "s",
    "MONGODB_ATLAS_ORG_ID": "o",
}

_S3_ENV_VARS = {
    **_ATLAS_ENV_VARS,
    "AWS_ROLE_ARN": "arn:aws:iam::role",
    "AWS_REGION": "us-east-1",
}


def test_collect_requirements_with_s3_backend() -> None:
    config = _config_with_s3()
    registry = {"mongodbatlas": _ATLAS_HINTS}
    reqs = collect_requirements(config, registry, {"mongodbatlas": "api_key"})
    assert "MONGODB_ATLAS_PUBLIC_KEY" in reqs.secrets
    assert "MONGODB_ATLAS_PRIVATE_KEY" in reqs.secrets
    assert "AWS_ROLE_ARN" in reqs.secrets
    assert "MONGODB_ATLAS_ORG_ID" in reqs.variables
    assert "AWS_REGION" in reqs.variables


def test_collect_requirements_without_s3() -> None:
    config = TfDoConfig(providers=[ProviderConstraint(name="mongodbatlas")])
    reqs = collect_requirements(config, {"mongodbatlas": _ATLAS_HINTS}, {"mongodbatlas": "api_key"})
    assert "AWS_ROLE_ARN" not in reqs.secrets
    assert "AWS_REGION" not in reqs.variables


def test_resolve_secrets_raises_on_missing() -> None:
    with pytest.raises(ValueError, match="missing secret values"):
        resolve_secret_values(["SECRET_A", "SECRET_B"], {"SECRET_A": "val"})


def test_two_env_workflow_generation(tmp_path: Path) -> None:
    _make_envs(tmp_path, ["dev", "prod"])
    config = _config_with_s3()
    calls, recorder = _gh_call_recorder()
    input_model = SyncGithubInput(
        settings=_settings(tmp_path),
        config=config,
        provider_hints_registry={"mongodbatlas": _ATLAS_HINTS},
        selected_bundles={"mongodbatlas": "api_key"},
        env_names=["dev", "prod"],
        owner_repo="org/repo",
        os_env=_S3_ENV_VARS,
        run_gh=recorder,
    )
    result = sync_github(input_model)

    assert len(result.workflow_files) == 2
    for env in ("dev", "prod"):
        wf_path = tmp_path / ".github/workflows" / f"tfdo-{env}.yml"
        assert wf_path.is_file()
        content = wf_path.read_text()
        assert f"paths: ['envs/{env}/**']" in content
        assert f"environment: {env}" in content
        assert ACTION_AWS_CREDS in content

    assert result.manual_workflow_path is not None
    assert result.manual_workflow_path.is_file()
    manual_content = result.manual_workflow_path.read_text()
    assert "options: [dev, prod]" in manual_content

    assert result.setup_action_path is not None
    assert result.setup_action_path.is_file()

    assert any("gh api" in c for c in calls)
    assert any("gh secret set" in c for c in calls)


def test_setup_action_reads_tf_version(tmp_path: Path) -> None:
    _make_envs(tmp_path, ["dev"])
    config = TfDoConfig(tf_version="1.10.0", providers=[ProviderConstraint(name="mongodbatlas")])
    calls, recorder = _gh_call_recorder()
    input_model = SyncGithubInput(
        settings=_settings(tmp_path),
        config=config,
        provider_hints_registry={"mongodbatlas": _ATLAS_HINTS},
        selected_bundles={"mongodbatlas": "api_key"},
        env_names=["dev"],
        owner_repo="org/repo",
        os_env=_ATLAS_ENV_VARS,
        run_gh=recorder,
    )
    result = sync_github(input_model)
    assert result.setup_action_path is not None
    content = result.setup_action_path.read_text()
    assert "default: '1.10.0'" in content
    assert "just-version:" in content
    assert ACTION_SETUP_UV in content
    assert f"tfdo @ {TFDO_DEFAULT_INSTALL}" in content


def test_setup_action_pypi_version(tmp_path: Path) -> None:
    _make_envs(tmp_path, ["dev"])
    config = TfDoConfig(ci=CiConfig(tfdo_install="==0.6.0"), providers=[ProviderConstraint(name="mongodbatlas")])
    _calls, recorder = _gh_call_recorder()
    input_model = _atlas_input(tmp_path, recorder, config=config)
    result = sync_github(input_model)
    assert result.setup_action_path is not None
    content = result.setup_action_path.read_text()
    assert "tfdo==0.6.0" in content
    assert "git+" not in content


def test_no_aws_step_without_s3_backend(tmp_path: Path) -> None:
    _make_envs(tmp_path, ["dev"])
    config = TfDoConfig(providers=[ProviderConstraint(name="mongodbatlas")])
    _calls, recorder = _gh_call_recorder()
    input_model = SyncGithubInput(
        settings=_settings(tmp_path),
        config=config,
        provider_hints_registry={"mongodbatlas": _ATLAS_HINTS},
        selected_bundles={"mongodbatlas": "api_key"},
        env_names=["dev"],
        owner_repo="org/repo",
        os_env=_ATLAS_ENV_VARS,
        run_gh=recorder,
    )
    sync_github(input_model)
    content = (tmp_path / ".github/workflows/tfdo-dev.yml").read_text()
    assert "aws-actions" not in content


def test_dry_run_produces_no_files_no_gh_calls(tmp_path: Path) -> None:
    _make_envs(tmp_path, ["dev"])
    config = _config_with_s3()
    calls, recorder = _gh_call_recorder()
    input_model = SyncGithubInput(
        settings=_settings(tmp_path),
        config=config,
        provider_hints_registry={"mongodbatlas": _ATLAS_HINTS},
        selected_bundles={"mongodbatlas": "api_key"},
        env_names=["dev"],
        owner_repo="org/repo",
        os_env=_S3_ENV_VARS,
        run_gh=recorder,
        dry_run=True,
    )
    result = sync_github(input_model)

    assert not calls
    assert not (tmp_path / ".github").exists()
    assert result.dry_run


def _atlas_input(tmp_path: Path, recorder: Callable[[str], tuple[bool, str]], **overrides: object) -> SyncGithubInput:
    defaults: dict[str, object] = {
        "settings": _settings(tmp_path),
        "config": TfDoConfig(providers=[ProviderConstraint(name="mongodbatlas")]),
        "provider_hints_registry": {"mongodbatlas": _ATLAS_HINTS},
        "selected_bundles": {"mongodbatlas": "api_key"},
        "env_names": ["dev"],
        "owner_repo": "org/repo",
        "os_env": _ATLAS_ENV_VARS,
        "run_gh": recorder,
    }
    defaults.update(overrides)
    return SyncGithubInput(**defaults)  # type: ignore[arg-type]


def test_section_markers_survive_regeneration(tmp_path: Path) -> None:
    _make_envs(tmp_path, ["dev"])
    _calls, recorder = _gh_call_recorder()
    input_model = _atlas_input(tmp_path, recorder)
    sync_github(input_model)
    wf_path = tmp_path / ".github/workflows/tfdo-dev.yml"

    custom_line = "\n# my custom job\ncustom-job:\n  runs-on: ubuntu-latest\n"
    wf_path.write_text(wf_path.read_text() + custom_line)

    sync_github(input_model)
    assert "my custom job" in wf_path.read_text()


def test_oidc_roles_inject_aws_role_arn(tmp_path: Path) -> None:
    _make_envs(tmp_path, ["dev", "prod"])
    config = TfDoConfig(
        providers=[ProviderConstraint(name="mongodbatlas")],
        backend=S3Backend(bucket="b", key="k", region="us-east-1"),
        ci=CiConfig(oidc_roles={"dev": "arn:dev", "prod": "arn:prod"}),
    )
    calls, recorder = _gh_call_recorder()
    input_model = SyncGithubInput(
        settings=_settings(tmp_path),
        config=config,
        provider_hints_registry={"mongodbatlas": _ATLAS_HINTS},
        selected_bundles={"mongodbatlas": "api_key"},
        env_names=["dev", "prod"],
        owner_repo="org/repo",
        os_env=_ATLAS_ENV_VARS,
        run_gh=recorder,
    )
    result = sync_github(input_model)
    assert len(result.env_sync_results) == 2
    dev_secrets = [c for c in calls if "gh secret set AWS_ROLE_ARN" in c and "--env dev" in c]
    prod_secrets = [c for c in calls if "gh secret set AWS_ROLE_ARN" in c and "--env prod" in c]
    assert len(dev_secrets) == 1
    assert "arn:dev" in dev_secrets[0]
    assert len(prod_secrets) == 1
    assert "arn:prod" in prod_secrets[0]


def test_resolve_env_vars_oidc_role_from_config(tmp_path: Path) -> None:
    config = TfDoConfig(
        backend=S3Backend(bucket="b", key="k", region="eu-west-1"),
        ci=CiConfig(oidc_roles={"dev": "arn:dev-role"}),
    )
    (tmp_path / "envs" / "dev").mkdir(parents=True)
    env_vars = _resolve_env_vars("dev", config, tmp_path, _settings(tmp_path), {})
    assert env_vars["AWS_ROLE_ARN"] == "arn:dev-role"
    assert env_vars["AWS_REGION"] == "eu-west-1"


def test_resolve_env_vars_os_env_overrides_config(tmp_path: Path) -> None:
    config = TfDoConfig(
        backend=S3Backend(bucket="b", key="k", region="eu-west-1"),
        ci=CiConfig(oidc_roles={"dev": "arn:config-role"}),
    )
    (tmp_path / "envs" / "dev").mkdir(parents=True)
    env_vars = _resolve_env_vars("dev", config, tmp_path, _settings(tmp_path), {"AWS_ROLE_ARN": "arn:os-role"})
    assert env_vars["AWS_ROLE_ARN"] == "arn:os-role"


def test_custom_discovery_pattern_affects_paths_trigger(tmp_path: Path) -> None:
    config = TfDoConfig(
        run_dir_discovery="environments/{env}",
        providers=[ProviderConstraint(name="mongodbatlas")],
    )
    (tmp_path / "environments" / "staging").mkdir(parents=True)
    _calls, recorder = _gh_call_recorder()
    input_model = SyncGithubInput(
        settings=_settings(tmp_path),
        config=config,
        provider_hints_registry={"mongodbatlas": _ATLAS_HINTS},
        selected_bundles={"mongodbatlas": "api_key"},
        env_names=["staging"],
        owner_repo="org/repo",
        os_env=_ATLAS_ENV_VARS,
        run_gh=recorder,
    )
    sync_github(input_model)
    content = (tmp_path / ".github/workflows/tfdo-staging.yml").read_text()
    assert "paths: ['environments/staging/**']" in content
