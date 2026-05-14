from __future__ import annotations

import json
import logging
import shlex
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
    _format_github_dotenv_line,
    _github_actions_environment_missing_stderr,
    _planned_secret_writes,
    _resolve_env_vars,
    collect_requirements,
    resolve_secret_values,
    resolve_variable_values,
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


def _configurable_gh(
    calls: list[str],
    *,
    existing_secrets_by_env: dict[str, set[str]] | None = None,
    remote_variables_by_env: dict[str, dict[str, str]] | None = None,
) -> Callable[[str], tuple[bool, str]]:
    existing_secrets_by_env = existing_secrets_by_env or {}
    remote_variables_by_env = remote_variables_by_env or {}

    def _env_token(script: str) -> str:
        marker = "--env "
        assert marker in script, script
        tail = script.split(marker, 1)[1]
        return shlex.split(tail, posix=True)[0]

    def recorder(script: str) -> tuple[bool, str]:
        calls.append(script)
        if "gh secret list" in script:
            env_name = _env_token(script)
            names = sorted(existing_secrets_by_env.get(env_name, set()))
            return True, json.dumps([{"name": n} for n in names])
        if "gh variable list" in script:
            env_name = _env_token(script)
            rows = sorted(remote_variables_by_env.get(env_name, {}).items())
            return True, json.dumps([{"name": k, "value": v} for k, v in rows])
        return True, ""

    return recorder


def _gh_call_recorder() -> tuple[list[str], Callable[[str], tuple[bool, str]]]:
    calls: list[str] = []

    def recorder(script: str) -> tuple[bool, str]:
        calls.append(script)
        if "gh secret list" in script or "gh variable list" in script:
            return True, "[]"
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
    assert reqs.optional_variables == []
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


def test_collect_requirements_variable_options_with_provider_attr() -> None:
    hints = _ATLAS_HINTS.model_copy(
        update={
            "variable_options": [
                VariableMapping(env="MONGODB_ATLAS_PROJECT_ID", tf_var="project_id"),
                VariableMapping(env="MONGODB_ATLAS_BASE_URL", tf_var="base_url", provider_attr="base_url"),
            ]
        }
    )
    config = TfDoConfig(providers=[ProviderConstraint(name="mongodbatlas")])
    reqs = collect_requirements(config, {"mongodbatlas": hints}, {"mongodbatlas": "api_key"})
    assert "MONGODB_ATLAS_BASE_URL" in reqs.optional_variables
    assert "MONGODB_ATLAS_PROJECT_ID" not in reqs.optional_variables


def test_sync_github_includes_provider_attr_variable_when_set(tmp_path: Path) -> None:
    _make_envs(tmp_path, ["dev"])
    hints = _ATLAS_HINTS.model_copy(
        update={
            "variable_options": [
                VariableMapping(env="MONGODB_ATLAS_BASE_URL", tf_var="base_url", provider_attr="base_url"),
            ]
        }
    )
    _calls, recorder = _gh_call_recorder()
    env_vars = {**_ATLAS_ENV_VARS, "MONGODB_ATLAS_BASE_URL": "https://cloud-dev.mongodb.com/"}
    input_model = _atlas_input(tmp_path, recorder, provider_hints_registry={"mongodbatlas": hints}, os_env=env_vars)
    result = sync_github(input_model)
    assert "MONGODB_ATLAS_BASE_URL" in result.env_sync_results[0].variables_set
    wf = (tmp_path / ".github/workflows/tfdo-dev.yml").read_text()
    assert "MONGODB_ATLAS_BASE_URL: ${{ vars.MONGODB_ATLAS_BASE_URL }}" in wf


def test_resolve_variable_values_optional_skips_without_warning(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    assert resolve_variable_values(["MONGODB_ATLAS_BASE_URL"], {}, warn_if_missing=False) == []
    assert not caplog.records


def test_resolve_secrets_raises_on_missing() -> None:
    with pytest.raises(ValueError, match="missing secret values"):
        resolve_secret_values(["SECRET_A", "SECRET_B"], {"SECRET_A": "val"})


def test_planned_secret_writes_skip_existing_until_replace() -> None:
    secrets, skipped = _planned_secret_writes(
        ["A", "B", "C"],
        {"A": "1", "B": "2", "C": "3"},
        {"B"},
        replace_existing_github_secrets=False,
    )
    assert [e.name for e in secrets] == ["A", "C"]
    assert skipped == ["B"]

    replace_all, skipped_when_forcing_replace = _planned_secret_writes(
        ["A", "B"], {"A": "1", "B": "2"}, {"B"}, replace_existing_github_secrets=True
    )
    assert [e.name for e in replace_all] == ["A", "B"]
    assert skipped_when_forcing_replace == []


def test_github_actions_environment_missing_stderr_matches_gh() -> None:
    sample = (
        "failed to get secrets: HTTP 404: Not Found "
        "(https://api.github.com/repos/EspenAlbert/tfdo-demo/environments/dummy/secrets?per_page=100)"
    )
    assert _github_actions_environment_missing_stderr(sample)
    assert not _github_actions_environment_missing_stderr("")
    assert not _github_actions_environment_missing_stderr("HTTP 403: Forbidden (https://example.com)")
    assert not _github_actions_environment_missing_stderr("failed to connect: dial tcp")


def test_github_environment_api_put_only_when_secret_list_404(tmp_path: Path) -> None:
    _make_envs(tmp_path, ["dev"])
    calls: list[str] = []
    list_attempt = [0]

    def recorder(script: str) -> tuple[bool, str]:
        calls.append(script)
        if "gh secret list" in script and "--env dev" in script:
            list_attempt[0] += 1
            if list_attempt[0] == 1:
                return (
                    False,
                    "failed to get secrets: HTTP 404: Not Found "
                    "(https://api.github.com/repos/org/repo/environments/dev/secrets?per_page=100)",
                )
            return True, "[]"
        if "gh api repos/org/repo/environments/dev" in script and "-X PUT" in script:
            return True, ""
        if "gh variable list" in script and "--env dev" in script:
            return True, "[]"
        return True, ""

    input_model = SyncGithubInput(
        settings=_settings(tmp_path),
        config=_config_with_s3(),
        provider_hints_registry={"mongodbatlas": _ATLAS_HINTS},
        selected_bundles={"mongodbatlas": "api_key"},
        env_names=["dev"],
        owner_repo="org/repo",
        os_env=_S3_ENV_VARS,
        run_gh=recorder,
    )
    sync_github(input_model)
    puts = [c for c in calls if "gh api repos/org/repo/environments/dev" in c and "-X PUT" in c]
    lists = [c for c in calls if "gh secret list" in c and "--env dev" in c]
    assert len(puts) == 1
    assert len(lists) == 2


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

    assert not any("gh api repos/" in c and "/environments/" in c for c in calls)
    assert any("gh secret set" in c for c in calls)
    secret_cmds = [c for c in calls if "gh secret set" in c]
    assert len(secret_cmds) == 2
    for cmd in secret_cmds:
        assert " -f " in cmd
        assert ".env" in cmd
        assert "--body" not in cmd
        assert _S3_ENV_VARS["AWS_ROLE_ARN"] not in cmd


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
    dev_secrets = [c for c in calls if "gh secret set" in c and "--env dev" in c]
    prod_secrets = [c for c in calls if "gh secret set" in c and "--env prod" in c]
    assert len(dev_secrets) == 1
    assert len(prod_secrets) == 1
    for cmd in (dev_secrets[0], prod_secrets[0]):
        assert " -f " in cmd
        assert ".env" in cmd
        assert "--body" not in cmd
    assert "arn:dev" not in dev_secrets[0]
    assert "arn:prod" not in prod_secrets[0]


def test_github_environment_secrets_are_skipped_when_remote_has_them_without_replace(tmp_path: Path) -> None:
    _make_envs(tmp_path, ["dev"])
    calls: list[str] = []
    all_secrets = {"MONGODB_ATLAS_PUBLIC_KEY", "MONGODB_ATLAS_PRIVATE_KEY", "AWS_ROLE_ARN"}
    recorder = _configurable_gh(calls, existing_secrets_by_env={"dev": all_secrets})
    input_model = SyncGithubInput(
        settings=_settings(tmp_path),
        config=_config_with_s3(),
        provider_hints_registry={"mongodbatlas": _ATLAS_HINTS},
        selected_bundles={"mongodbatlas": "api_key"},
        env_names=["dev"],
        owner_repo="org/repo",
        os_env=_S3_ENV_VARS,
        run_gh=recorder,
        replace_existing_github_secrets=False,
    )
    sync_github(input_model)
    assert not any("gh secret set" in c for c in calls)


def test_github_environment_secrets_overwritten_when_replace_flag_set(tmp_path: Path) -> None:
    _make_envs(tmp_path, ["dev"])
    calls: list[str] = []
    all_secrets = {"MONGODB_ATLAS_PUBLIC_KEY", "MONGODB_ATLAS_PRIVATE_KEY", "AWS_ROLE_ARN"}
    recorder = _configurable_gh(calls, existing_secrets_by_env={"dev": all_secrets})
    input_model = SyncGithubInput(
        settings=_settings(tmp_path),
        config=_config_with_s3(),
        provider_hints_registry={"mongodbatlas": _ATLAS_HINTS},
        selected_bundles={"mongodbatlas": "api_key"},
        env_names=["dev"],
        owner_repo="org/repo",
        os_env=_S3_ENV_VARS,
        run_gh=recorder,
        replace_existing_github_secrets=True,
    )
    sync_github(input_model)
    secret_sets = [c for c in calls if "gh secret set" in c]
    assert len(secret_sets) == 1
    assert " -f " in secret_sets[0]
    assert "arn:aws:iam::role" not in secret_sets[0]


def test_github_variables_matching_remote_are_not_set(tmp_path: Path) -> None:
    _make_envs(tmp_path, ["dev"])
    calls: list[str] = []
    recorder = _configurable_gh(
        calls,
        remote_variables_by_env={"dev": {"MONGODB_ATLAS_ORG_ID": "o"}},
    )

    def _no_prompt(*_args: object) -> bool:
        raise AssertionError("variable prompt should not run when remote matches resolved local value")

    input_model = _atlas_input(tmp_path, recorder, github_variable_changed=_no_prompt)
    sync_github(input_model)
    assert not any("gh variable set" in c for c in calls)


def test_github_variable_change_declined_skips_writes(tmp_path: Path) -> None:
    _make_envs(tmp_path, ["dev"])
    calls: list[str] = []
    recorder = _configurable_gh(calls, remote_variables_by_env={"dev": {"MONGODB_ATLAS_ORG_ID": "remote-org"}})
    input_model = _atlas_input(tmp_path, recorder, github_variable_changed=lambda *_n: False)
    sync_github(input_model)
    assert not any("gh variable set" in c for c in calls)


def test_github_variable_change_accept_updates(tmp_path: Path) -> None:
    _make_envs(tmp_path, ["dev"])
    calls: list[str] = []
    recorder = _configurable_gh(calls, remote_variables_by_env={"dev": {"MONGODB_ATLAS_ORG_ID": "remote-org"}})
    input_model = _atlas_input(tmp_path, recorder, github_variable_changed=lambda *_n: True)
    sync_github(input_model)
    var_cmds = [c for c in calls if "gh variable set" in c]
    assert len(var_cmds) == 1
    assert " -f " in var_cmds[0]
    assert "--body" not in var_cmds[0]
    assert "remote-org" not in var_cmds[0]


def test_format_github_dotenv_line_escapes() -> None:
    assert _format_github_dotenv_line("X", 'say "hi"') == 'X="say \\"hi\\""'
    assert "\\n" in _format_github_dotenv_line("M", "a\nb")


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
