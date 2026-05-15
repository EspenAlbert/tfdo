from __future__ import annotations

import json
import logging
import os
import shlex
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Literal, NamedTuple

from ask_shell._internal.interactive import confirm
from ask_shell.shell import ShellError, run_and_wait
from pydantic import BaseModel, Field
from zero_3rdparty import file_utils
from zero_3rdparty.sections import CommentConfig, replace_sections

from tfdo._internal.boot.oidc_bootstrap import OidcWizardResult, run_oidc_wizard
from tfdo._internal.config.config_file import load_optional_env_vars_from_files, save_config
from tfdo._internal.config.config_model import TFDO_DEFAULT_INSTALL, CiConfig, S3Backend, TfDoConfig
from tfdo._internal.config.provider_hints import (
    AuthBundle,
    ProviderHints,
)
from tfdo._internal.models import TfDoBaseInput
from tfdo._internal.settings import TfDoSettings

logger = logging.getLogger(__name__)


def prompt_github_variable_update(name: str, remote_value: str, proposed_value: str) -> bool:
    return confirm(
        f"GitHub variable {name} differs "
        f"(remote={remote_value!r}; local/tfdo resolves to={proposed_value!r}). "
        f"Update this variable on GitHub?",
        default=False,
    )


TOOL_NAME = "tfdo"
YAML_COMMENT_CONFIG = CommentConfig("#")

GH_WORKFLOWS_DIR = ".github/workflows"
GH_ACTIONS_DIR = ".github/actions/tfdo-setup"

# SHA-pinned action versions (update these when upgrading)
ACTION_CHECKOUT = "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd"  # v6.0.2
ACTION_AWS_CREDS = "aws-actions/configure-aws-credentials@d979d5b3a71173a29b74b5b88418bfda9437d885"  # v6.1.1
ACTION_SETUP_JUST = "extractions/setup-just@53165ef7e734c5c07cb06b3c8e7b647c5aa16db3"  # v4.0.0
ACTION_SETUP_UV = "astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b"  # v8.1.0
ACTION_MISE = "jdx/mise-action@1648a7812b9aeae629881980618f079932869151"  # v4.0.1


class SecretEntry(NamedTuple):
    name: str
    value: str


class VariableEntry(NamedTuple):
    name: str
    value: str


class EnvSyncResult(BaseModel):
    env: str
    secrets_set: list[str] = Field(default_factory=list)
    secrets_failed: list[str] = Field(default_factory=list)
    secrets_skipped_existing: list[str] = Field(default_factory=list)
    variables_set: list[str] = Field(default_factory=list)
    variables_failed: list[str] = Field(default_factory=list)
    variables_unchanged: list[str] = Field(default_factory=list)
    variables_update_declined: list[str] = Field(default_factory=list)


class SyncGithubInput(TfDoBaseInput):
    config: TfDoConfig = Field(default_factory=TfDoConfig)
    provider_hints_registry: dict[str, ProviderHints] = Field(default_factory=dict)
    selected_bundles: dict[str, str] = Field(default_factory=dict)
    env_names: list[str] = Field(default_factory=list)
    owner_repo: str = ""
    os_env: dict[str, str] = Field(default_factory=dict)
    run_gh: Callable[[str], tuple[bool, str]] | None = None
    replace_existing_github_secrets: bool = False
    github_variable_changed: Callable[[str, str, str], bool] = prompt_github_variable_update
    oidc: bool = False


class SyncGithubResult(BaseModel):
    workflow_files: list[Path] = Field(default_factory=list)
    setup_action_path: Path | None = None
    manual_workflow_path: Path | None = None
    env_sync_results: list[EnvSyncResult] = Field(default_factory=list)
    dry_run: bool = False


class CollectedRequirements(NamedTuple):
    secrets: list[str]
    variables: list[str]
    optional_variables: list[str]


def collect_requirements(
    config: TfDoConfig,
    registry: dict[str, ProviderHints],
    selected_bundles: dict[str, str],
) -> CollectedRequirements:
    secrets: list[str] = []
    variables: list[str] = []
    optional_variables: list[str] = []
    for provider in config.providers:
        hints = registry.get(provider.name)
        if hints is None:
            continue
        bundles_by_name = {b.name: b for b in hints.auth_bundles}
        bundle_name = selected_bundles.get(provider.name)
        bundle: AuthBundle | None = bundles_by_name.get(bundle_name) if bundle_name else None
        bundle = bundle or (hints.auth_bundles[0] if hints.auth_bundles else None)
        if bundle:
            reqs = bundle.effective_requirements(bundles_by_name)
            secrets.extend(reqs.secrets)
            variables.extend(reqs.variables)
        for vm in hints.auth_variables:
            variables.append(vm.env)
        for vm in hints.variable_options:
            if vm.provider_attr is not None:
                optional_variables.append(vm.env)

    match config.backend:
        case S3Backend():
            secrets.append("AWS_ROLE_ARN")
            variables.append("AWS_REGION")

    return CollectedRequirements(
        secrets=list(dict.fromkeys(secrets)),
        variables=list(dict.fromkeys(variables)),
        optional_variables=list(dict.fromkeys(optional_variables)),
    )


def _missing_secret_values_message(missing: list[str]) -> str:
    msg = (
        f"missing secret values for: {', '.join(missing)}. "
        "Set them in env_var files or shell environment before retrying."
    )
    if "AWS_ROLE_ARN" in missing:
        msg += (
            " For AWS_ROLE_ARN with an S3 backend, run `tfdo sync gh --oidc` to provision IAM roles "
            "for GitHub Actions, this will save their ARNs in tfdo.yaml, or set AWS_ROLE_ARN yourself."
        )
    return msg


def resolve_secret_values(secret_names: list[str], env_vars: dict[str, str]) -> list[SecretEntry]:
    missing = [name for name in secret_names if name not in env_vars]
    if missing:
        raise ValueError(_missing_secret_values_message(missing))
    return [SecretEntry(name, env_vars[name]) for name in secret_names]


def resolve_variable_values(
    variable_names: list[str], env_vars: dict[str, str], *, warn_if_missing: bool = True
) -> list[VariableEntry]:
    entries: list[VariableEntry] = []
    for name in variable_names:
        if name in env_vars:
            entries.append(VariableEntry(name, env_vars[name]))
        elif warn_if_missing:
            logger.warning(f"variable {name} not found in env_vars, skipping")
    return entries


def _planned_secret_writes(
    required_names: list[str],
    env_vars: dict[str, str],
    existing_remote_names: set[str],
    replace_existing_github_secrets: bool,
) -> tuple[list[SecretEntry], list[str]]:
    skipped: list[str] = []
    pending_names: list[str] = []
    for name in required_names:
        if name in existing_remote_names and not replace_existing_github_secrets:
            skipped.append(name)
            continue
        pending_names.append(name)
    missing = [n for n in pending_names if n not in env_vars]
    if missing:
        raise ValueError(_missing_secret_values_message(missing))
    return [SecretEntry(n, env_vars[n]) for n in pending_names], skipped


def _parse_gh_json_records(raw: str) -> list[dict[str, str]]:
    stripped = raw.strip()
    return json.loads(stripped) if stripped else []


def _github_actions_environment_missing_stderr(stderr_or_msg: str) -> bool:
    """Best-effort match for gh when the Actions deployment environment does not exist."""
    lowered = stderr_or_msg.lower()
    return (
        "404" in stderr_or_msg
        and "not found" in lowered
        and ("environments/" in lowered or "failed to get secrets" in lowered)
    )


def _gh_secret_list_names_json(env: str, run_gh: Callable[[str], tuple[bool, str]]) -> tuple[bool, str]:
    return run_gh(f"gh secret list --env {shlex.quote(env)} --json name")


def _secret_names_from_gh_list_json(payload: str) -> set[str]:
    return {row["name"] for row in _parse_gh_json_records(payload)}


def _remote_env_secret_names_with_optional_bootstrap(
    owner_repo: str, env: str, run_gh: Callable[[str], tuple[bool, str]]
) -> set[str]:
    ok, raw = _gh_secret_list_names_json(env, run_gh)
    if ok:
        return _secret_names_from_gh_list_json(raw)

    if not _github_actions_environment_missing_stderr(raw):
        raise ValueError(f"failed to list GitHub secrets for environment {env!r}: {raw}")

    logger.info(
        f"GitHub Actions environment {env!r} not found ({raw.strip()}); "
        f"creating it with gh api repos/.../environments/..."
    )
    api_ok, api_msg = run_gh(f"gh api repos/{owner_repo}/environments/{env} -X PUT")
    if not api_ok:
        logger.warning(f"failed to create GitHub Actions environment {env!r}: {api_msg}")

    ok_retry, raw_retry = _gh_secret_list_names_json(env, run_gh)
    if not ok_retry:
        raise ValueError(
            f"failed to list GitHub secrets for environment {env!r} after creating environment: {raw_retry}"
        )
    return _secret_names_from_gh_list_json(raw_retry)


def _remote_env_variables(env: str, run_gh: Callable[[str], tuple[bool, str]]) -> dict[str, str]:
    ok, raw = run_gh(f"gh variable list --env {shlex.quote(env)} --json name,value")
    if not ok:
        raise ValueError(f"failed to list GitHub variables for environment {env!r}: {raw}")
    rows = _parse_gh_json_records(raw)
    return {row["name"]: row["value"] for row in rows}


def _format_github_dotenv_line(key: str, value: str) -> str:
    """One dotenv-compatible line as ``KEY="..."`` for gh ``--env-file``."""
    escaped = value.replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n").replace('"', '\\"')
    return f'{key}="{escaped}"'


def _batch_gh_via_dotenv_tempfile(
    *,
    gh_resource: Literal["secret", "variable"],
    github_env: str,
    pairs: list[tuple[str, str]],
    run_gh: Callable[[str], tuple[bool, str]],
) -> tuple[bool, str]:
    if not pairs:
        return True, ""
    fd, raw_path_str = tempfile.mkstemp(prefix="tfdo-gh-sync-", suffix=".env")
    os.close(fd)
    path = Path(raw_path_str)
    try:
        path.write_text("".join(f"{_format_github_dotenv_line(k, v)}\n" for k, v in pairs))
        cmd = f"gh {gh_resource} set -f {shlex.quote(str(path))} --env {shlex.quote(github_env)}"
        return run_gh(cmd)
    finally:
        path.unlink(missing_ok=True)


def _render_env_workflow(
    env: str,
    config: TfDoConfig,
    secrets: list[str],
    variables: list[str],
    optional_variables: list[str],
) -> dict[str, str]:
    has_s3_backend = isinstance(config.backend, S3Backend)
    prefix = config.env_path_prefix

    header_lines = [
        f"name: 'tfdo: {env}'",
        "",
        "on:",
        "  push:",
        "    branches: [main]",
        f"    paths: ['{prefix}/{env}/**']",
        "  pull_request:",
        f"    paths: ['{prefix}/{env}/**']",
    ]

    env_lines: list[str] = []
    for s in secrets:
        env_lines.append(f"  {s}: ${{{{ secrets.{s} }}}}")
    for v in dict.fromkeys([*variables, *optional_variables]):
        env_lines.append(f"  {v}: ${{{{ vars.{v} }}}}")
    env_block = "env:\n" + "\n".join(env_lines) if env_lines else ""

    aws_step = ""
    if has_s3_backend:
        aws_step = (
            "      - name: Configure AWS Credentials\n"
            f"        uses: {ACTION_AWS_CREDS}\n"
            "        with:\n"
            "          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}\n"
            "          aws-region: ${{ vars.AWS_REGION }}"
        )

    plan_steps = [
        f"      - uses: {ACTION_CHECKOUT}",
        "      - uses: ./.github/actions/tfdo-setup",
    ]
    if aws_step:
        plan_steps.append(aws_step)
    plan_steps.append(f"      - run: just {env} plan")

    plan_lines = [
        "jobs:",
        "  plan:",
        "    runs-on: ubuntu-latest",
        f"    environment: {env}",
        "    permissions:",
        "      id-token: write",
        "      contents: read",
        "      pull-requests: write",
        "    steps:",
        *plan_steps,
    ]

    apply_steps = [
        f"      - uses: {ACTION_CHECKOUT}",
        "      - uses: ./.github/actions/tfdo-setup",
    ]
    if aws_step:
        apply_steps.append(aws_step)
    apply_steps.append(f"      - run: just {env} apply --auto-approve")

    apply_lines = [
        "  apply:",
        "    if: github.event_name == 'push'",
        "    runs-on: ubuntu-latest",
        f"    environment: {env}",
        "    needs: [plan]",
        "    permissions:",
        "      id-token: write",
        "      contents: read",
        "    steps:",
        *apply_steps,
    ]

    return {
        "header": "\n".join(header_lines),
        "env": env_block,
        "job-plan": "\n".join(plan_lines),
        "job-apply": "\n".join(apply_lines),
    }


def _render_manual_workflow(env_names: list[str], config: TfDoConfig) -> dict[str, str]:
    has_s3_backend = isinstance(config.backend, S3Backend)
    env_choices = ", ".join(env_names)

    dispatch_lines = [
        "run-name: \"tfdo: env=${{ github.event.inputs.env }}, action=${{ github.event.inputs.action }}${{ github.event.inputs.run_dir && format(', run_dir={0}', github.event.inputs.run_dir) || '' }}${{ github.event.inputs.extra_args && format(', extra_args={0}', github.event.inputs.extra_args) || '' }}\"",
        "",
        "on:",
        "  workflow_dispatch:",
        "    inputs:",
        "      env:",
        "        description: Environment",
        "        required: true",
        "        type: choice",
        f"        options: [{env_choices}]",
        "      action:",
        "        description: Action to run",
        "        required: true",
        "        type: choice",
        "        options: [plan, apply, destroy]",
        "      run_dir:",
        "        description: Run directory (optional)",
        "        required: false",
        "        type: string",
        "      extra_args:",
        "        description: Extra arguments (optional)",
        "        required: false",
        "        type: string",
    ]

    steps = [
        f"      - uses: {ACTION_CHECKOUT}",
        "      - uses: ./.github/actions/tfdo-setup",
    ]
    if has_s3_backend:
        steps.append(
            "      - name: Configure AWS Credentials\n"
            f"        uses: {ACTION_AWS_CREDS}\n"
            "        with:\n"
            "          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}\n"
            "          aws-region: ${{ vars.AWS_REGION }}"
        )
    # Empty optional inputs produce empty strings; build the command conditionally
    run_cmd = "just ${{ github.event.inputs.env }} ${{ github.event.inputs.action }}"
    run_cmd += (
        " ${{ (github.event.inputs.action == 'apply' || github.event.inputs.action == 'destroy') "
        "&& '--auto-approve' || '' }}"
    )
    run_cmd += " ${{ github.event.inputs.run_dir && format('--app {0}', github.event.inputs.run_dir) || '' }}"
    run_cmd += " ${{ github.event.inputs.extra_args }}"
    steps.append(f"      - run: {run_cmd}")

    job_lines = [
        "jobs:",
        "  manual:",
        "    runs-on: ubuntu-latest",
        "    environment: ${{ github.event.inputs.env }}",
        "    permissions:",
        "      id-token: write",
        "      contents: read",
        "    steps:",
        *steps,
    ]

    return {
        "dispatch": "\n".join(dispatch_lines),
        "job-manual": "\n".join(job_lines),
    }


def _tfdo_install_expr(tfdo_install: str) -> str:
    """Build the pip install argument from the config value.

    ``git+`` prefixed values are VCS URLs → ``tfdo @ <url>``.
    Everything else is a PyPI version specifier → ``tfdo<spec>``.
    """
    if tfdo_install.startswith("git+"):
        return f"tfdo @ {tfdo_install}"
    return f"tfdo{tfdo_install}"


def _render_setup_action(config: TfDoConfig) -> dict[str, str]:
    tf_version_default = config.tf_version or "latest"
    tf_gh = "${{ inputs.terraform-version == '*' && 'latest' || inputs.terraform-version }}"
    tfdo_install = config.ci.tfdo_install if config.ci else TFDO_DEFAULT_INSTALL
    install_expr = _tfdo_install_expr(tfdo_install)
    setup_lines = [
        "name: tfdo-setup",
        "description: Install just, mise (terraform), uv, and tfdo for tfdo workflows",
        "inputs:",
        "  terraform-version:",
        "    description: Terraform version",
        f"    default: '{tf_version_default}'",
        "  just-version:",
        "    description: Just version",
        "    default: '*'",
        "  uv-version:",
        "    description: uv version",
        "    default: '*'",
        "runs:",
        "  using: composite",
        "  steps:",
        f"    - uses: {ACTION_SETUP_JUST}",
        "      with:",
        "        just-version: ${{ inputs.just-version }}",
        f"    - uses: {ACTION_MISE}",
        "      with:",
        f"        install_args: terraform@{tf_gh}",
        f"    - run: mise use -g terraform@{tf_gh}",
        "      shell: bash",
        f"    - uses: {ACTION_SETUP_UV}",
        "      with:",
        "        version: ${{ inputs.uv-version }}",
        f"    - run: uv tool install '{install_expr}'",
        "      shell: bash",
    ]
    return {"setup": "\n".join(setup_lines)}


def _write_workflow_file(path: Path, sections: dict[str, str], dry_run: bool) -> bool:
    if dry_run:
        logger.info(f"dry-run: would write {path}")
        return False
    existing = path.read_text() if path.is_file() else ""
    updated = replace_sections(existing, sections, TOOL_NAME, YAML_COMMENT_CONFIG)
    changed = updated != existing
    if changed or not path.is_file():
        file_utils.ensure_parents_write_text(path, updated)
    return changed


def _default_run_gh(script: str) -> tuple[bool, str]:
    try:
        result = run_and_wait(script, skip_progress_output=True)
        return True, result.stdout_one_line
    except ShellError as e:
        return False, str(e)


def _resolve_env_vars(
    env: str,
    config: TfDoConfig,
    work_dir: Path,
    settings: TfDoSettings,
    os_env: dict[str, str],
) -> dict[str, str]:
    """Merge os.environ with per-env env_var files and config-derived values.

    Priority (lowest to highest): config defaults, os env, env_var files.
    """
    defaults: dict[str, str] = {}
    if config.ci and (role_arn := config.ci.oidc_roles.get(env)):
        defaults["AWS_ROLE_ARN"] = role_arn
    match config.backend:
        case S3Backend(region=region) if region:
            defaults["AWS_REGION"] = region
    merged = {**defaults, **os_env}
    env_dir = config.env_base_dir(work_dir) / env
    file_vars = load_optional_env_vars_from_files(env_dir, settings, log=logger)
    merged.update(file_vars)
    return merged


def _record_secret_writes(
    env: str,
    secret_writes: list[SecretEntry],
    run_gh: Callable[[str], tuple[bool, str]],
    result: EnvSyncResult,
) -> None:
    if not secret_writes:
        return
    pairs = [(e.name, e.value) for e in secret_writes]
    ok, msg = _batch_gh_via_dotenv_tempfile(gh_resource="secret", github_env=env, pairs=pairs, run_gh=run_gh)
    if ok:
        result.secrets_set.extend(entry.name for entry in secret_writes)
    else:
        logger.warning(f"failed to set secrets for env {env} using temporary env file: {msg}")
        result.secrets_failed.extend(entry.name for entry in secret_writes)


def _record_variable_writes(
    env: str,
    variable_entries: list[VariableEntry],
    remote_vars: dict[str, str],
    github_variable_changed: Callable[[str, str, str], bool],
    run_gh: Callable[[str], tuple[bool, str]],
    result: EnvSyncResult,
) -> None:
    pending: list[VariableEntry] = []
    for entry in variable_entries:
        if entry.name not in remote_vars:
            pending.append(entry)
            continue

        github_value = remote_vars[entry.name]
        if github_value == entry.value:
            result.variables_unchanged.append(entry.name)
            continue

        if github_variable_changed(entry.name, github_value, entry.value):
            pending.append(entry)
        else:
            result.variables_update_declined.append(entry.name)

    if not pending:
        return

    pairs = [(e.name, e.value) for e in pending]
    ok, msg = _batch_gh_via_dotenv_tempfile(gh_resource="variable", github_env=env, pairs=pairs, run_gh=run_gh)
    if ok:
        result.variables_set.extend(entry.name for entry in pending)
    else:
        logger.warning(f"failed to set variables for env {env} using temporary env file: {msg}")
        result.variables_failed.extend(entry.name for entry in pending)


def sync_env_secrets_and_variables(
    owner_repo: str,
    env: str,
    required_secret_names: list[str],
    env_vars_for_secrets: dict[str, str],
    variable_entries: list[VariableEntry],
    dry_run: bool,
    replace_existing_github_secrets: bool,
    github_variable_changed: Callable[[str, str, str], bool],
    run_gh: Callable[[str], tuple[bool, str]],
) -> EnvSyncResult:
    result = EnvSyncResult(env=env)
    if dry_run:
        logger.info(
            f"dry-run: would list secrets for Actions environment {env!r}; would create that environment "
            f"via gh api only if secret list fails with a missing-environment error (typically HTTP 404); "
            f"would write a short-lived .env file and use gh -f (values not passed on the command line); "
            f"would set only absent secrets ({'or all when --replace' if replace_existing_github_secrets else 'no overwrites'}); "
            f"would prompt before changing variables that differ."
        )
        return result

    remote_secret_names = _remote_env_secret_names_with_optional_bootstrap(owner_repo, env, run_gh)
    logger.info(
        f"GitHub environment {env!r}: {len(remote_secret_names)} existing secret(s): "
        f"{', '.join(sorted(remote_secret_names))}"
    )
    remote_vars = _remote_env_variables(env, run_gh)
    logger.info(f"GitHub environment {env!r}: existing variable name(s): {', '.join(sorted(remote_vars))}")

    try:
        secret_writes, secrets_skipped = _planned_secret_writes(
            required_secret_names,
            env_vars_for_secrets,
            remote_secret_names,
            replace_existing_github_secrets,
        )
    except ValueError as e:
        raise ValueError(f"{env}: {e}") from e

    result.secrets_skipped_existing.extend(secrets_skipped)
    for skipped_name in secrets_skipped:
        logger.info(f"skipped GitHub secret {skipped_name} (already set in environment {env}; use sync --replace)")

    _record_secret_writes(env, secret_writes, run_gh, result)
    _record_variable_writes(env, variable_entries, remote_vars, github_variable_changed, run_gh, result)

    return result


def _needs_oidc_setup(config: TfDoConfig, reqs: CollectedRequirements, env_names: list[str]) -> bool:
    """Check if OIDC setup is needed: S3 backend requires AWS_ROLE_ARN but roles are missing."""
    if "AWS_ROLE_ARN" not in reqs.secrets:
        return False
    ci = config.ci
    if ci is None:
        return True
    return any(env not in ci.oidc_roles for env in env_names)


def _apply_oidc_result(config: TfDoConfig, oidc_result: OidcWizardResult) -> None:
    ci = config.ci or CiConfig()
    ci.oidc = True
    ci.repo_org = oidc_result.repo_org
    ci.repo_name = oidc_result.repo_name
    if oidc_result.oidc_roles:
        ci.oidc_roles = oidc_result.oidc_roles
    config.ci = ci


def sync_github(input_model: SyncGithubInput) -> SyncGithubResult:
    work_dir = input_model.settings.work_dir
    config = input_model.config
    env_names = input_model.env_names or [p.name for p in config.envs(work_dir)]
    run_gh = input_model.run_gh or _default_run_gh

    reqs = collect_requirements(config, input_model.provider_hints_registry, input_model.selected_bundles)

    if input_model.oidc and _needs_oidc_setup(config, reqs, env_names):
        ci = config.ci or CiConfig()
        match config.backend:
            case S3Backend(bucket=backend_bucket):
                pass
            case _:
                backend_bucket = None
        oidc_result = run_oidc_wizard(
            input_model.settings,
            org=ci.repo_org or "",
            repo=ci.repo_name or "",
            backend_bucket=backend_bucket,
        )
        _apply_oidc_result(config, oidc_result)
        save_config(work_dir, config)

    result = SyncGithubResult(dry_run=input_model.dry_run)

    for env in env_names:
        sections = _render_env_workflow(env, config, reqs.secrets, reqs.variables, reqs.optional_variables)
        path = work_dir / GH_WORKFLOWS_DIR / f"tfdo-{env}.yml"
        _write_workflow_file(path, sections, input_model.dry_run)
        result.workflow_files.append(path)
        logger.info(f"workflow: {path}")

    manual_sections = _render_manual_workflow(env_names, config)
    manual_path = work_dir / GH_WORKFLOWS_DIR / "tfdo-manual.yml"
    _write_workflow_file(manual_path, manual_sections, input_model.dry_run)
    result.manual_workflow_path = manual_path
    logger.info(f"manual workflow: {manual_path}")

    setup_sections = _render_setup_action(config)
    setup_path = work_dir / GH_ACTIONS_DIR / "action.yml"
    _write_workflow_file(setup_path, setup_sections, input_model.dry_run)
    result.setup_action_path = setup_path
    logger.info(f"setup action: {setup_path}")

    for env in env_names:
        env_vars = _resolve_env_vars(env, config, work_dir, input_model.settings, input_model.os_env)
        variable_entries = [
            *resolve_variable_values(reqs.variables, env_vars),
            *resolve_variable_values(reqs.optional_variables, env_vars, warn_if_missing=False),
        ]
        env_result = sync_env_secrets_and_variables(
            input_model.owner_repo,
            env,
            reqs.secrets,
            env_vars,
            variable_entries,
            input_model.dry_run,
            input_model.replace_existing_github_secrets,
            input_model.github_variable_changed,
            run_gh,
        )
        result.env_sync_results.append(env_result)
        logger.info(f"env {env}: secrets={len(env_result.secrets_set)}, variables={len(env_result.variables_set)}")
        if env_result.variables_set:
            logger.info(f"env {env}: variables synced: {', '.join(sorted(env_result.variables_set))}")

    return result
