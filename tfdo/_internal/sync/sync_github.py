from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from ask_shell.shell import ShellError, run_and_wait
from pydantic import BaseModel, Field
from zero_3rdparty import file_utils
from zero_3rdparty.sections import CommentConfig, replace_sections

from tfdo._internal.config.config_file import load_optional_env_vars_from_files
from tfdo._internal.config.config_model import TFDO_DEFAULT_INSTALL, S3Backend, TfDoConfig
from tfdo._internal.config.provider_hints import (
    AuthBundle,
    ProviderHints,
)
from tfdo._internal.models import TfDoBaseInput
from tfdo._internal.settings import TfDoSettings

logger = logging.getLogger(__name__)

TOOL_NAME = "tfdo"
YAML_COMMENT_CONFIG = CommentConfig("#")

GH_WORKFLOWS_DIR = ".github/workflows"
GH_ACTIONS_DIR = ".github/actions/tfdo-setup"

# SHA-pinned action versions (update these when upgrading)
ACTION_CHECKOUT = "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd"  # v6.0.2
ACTION_AWS_CREDS = "aws-actions/configure-aws-credentials@d979d5b3a71173a29b74b5b88418bfda9437d885"  # v6.1.1
ACTION_SETUP_JUST = "extractions/setup-just@53165ef7e734c5c07cb06b3c8e7b647c5aa16db3"  # v4.0.0
ACTION_SETUP_TERRAFORM = "hashicorp/setup-terraform@dfe3c3f87815947d99a8997f908cb6525fc44e9e"  # v4.0.1
ACTION_SETUP_UV = "astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b"  # v8.1.0


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
    variables_set: list[str] = Field(default_factory=list)
    variables_failed: list[str] = Field(default_factory=list)


class SyncGithubInput(TfDoBaseInput):
    config: TfDoConfig = Field(default_factory=TfDoConfig)
    provider_hints_registry: dict[str, ProviderHints] = Field(default_factory=dict)
    selected_bundles: dict[str, str] = Field(default_factory=dict)
    env_names: list[str] = Field(default_factory=list)
    owner_repo: str = ""
    os_env: dict[str, str] = Field(default_factory=dict)
    run_gh: Callable[[str], tuple[bool, str]] | None = None


class SyncGithubResult(BaseModel):
    workflow_files: list[Path] = Field(default_factory=list)
    setup_action_path: Path | None = None
    manual_workflow_path: Path | None = None
    env_sync_results: list[EnvSyncResult] = Field(default_factory=list)
    dry_run: bool = False


class CollectedRequirements(NamedTuple):
    secrets: list[str]
    variables: list[str]


def collect_requirements(
    config: TfDoConfig,
    registry: dict[str, ProviderHints],
    selected_bundles: dict[str, str],
) -> CollectedRequirements:
    secrets: list[str] = []
    variables: list[str] = []
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

    match config.backend:
        case S3Backend():
            secrets.append("AWS_ROLE_ARN")
            variables.append("AWS_REGION")

    return CollectedRequirements(
        secrets=list(dict.fromkeys(secrets)),
        variables=list(dict.fromkeys(variables)),
    )


def resolve_secret_values(secret_names: list[str], env_vars: dict[str, str]) -> list[SecretEntry]:
    missing = [name for name in secret_names if name not in env_vars]
    if missing:
        raise ValueError(
            f"missing secret values for: {', '.join(missing)}. "
            "Set them in env_var files or shell environment before retrying."
        )
    return [SecretEntry(name, env_vars[name]) for name in secret_names]


def resolve_variable_values(variable_names: list[str], env_vars: dict[str, str]) -> list[VariableEntry]:
    entries: list[VariableEntry] = []
    for name in variable_names:
        if name in env_vars:
            entries.append(VariableEntry(name, env_vars[name]))
        else:
            logger.warning(f"variable {name} not found in env_vars, skipping")
    return entries


def _render_env_workflow(
    env: str,
    config: TfDoConfig,
    secrets: list[str],
    variables: list[str],
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
    for v in variables:
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
        "name: 'tfdo: ${{ inputs.action }} ${{ inputs.env }}'",
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
    run_cmd = "just ${{ inputs.env }} ${{ inputs.action }}"
    run_cmd += " ${{ inputs.run_dir && format('--app {0}', inputs.run_dir) || '' }}"
    run_cmd += " ${{ inputs.extra_args }}"
    steps.append(f"      - run: {run_cmd}")

    job_lines = [
        "jobs:",
        "  manual:",
        "    runs-on: ubuntu-latest",
        "    environment: ${{ inputs.env }}",
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
    tfdo_install = config.ci.tfdo_install if config.ci else TFDO_DEFAULT_INSTALL
    install_expr = _tfdo_install_expr(tfdo_install)
    setup_lines = [
        "name: tfdo-setup",
        "description: Install terraform, just, uv, and tfdo for tfdo workflows",
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
        f"    - uses: {ACTION_SETUP_TERRAFORM}",
        "      with:",
        "        terraform_version: ${{ inputs.terraform-version }}",
        f"    - uses: {ACTION_SETUP_UV}",
        "      with:",
        "        version: ${{ inputs.uv-version }}",
        f"    - run: uv pip install --system '{install_expr}'",
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


def sync_env_secrets_and_variables(
    owner_repo: str,
    env: str,
    secret_entries: list[SecretEntry],
    variable_entries: list[VariableEntry],
    dry_run: bool,
    run_gh: Callable[[str], tuple[bool, str]],
) -> EnvSyncResult:
    result = EnvSyncResult(env=env)
    if dry_run:
        logger.info(
            f"dry-run: would create env {env} and set {len(secret_entries)} secrets, {len(variable_entries)} variables"
        )
        return result

    run_gh(f"gh api repos/{owner_repo}/environments/{env} -X PUT")

    for entry in secret_entries:
        ok, msg = run_gh(f"gh secret set {entry.name} --env {env} --body '{entry.value}'")
        if ok:
            result.secrets_set.append(entry.name)
        else:
            logger.warning(f"failed to set secret {entry.name} for env {env}: {msg}")
            result.secrets_failed.append(entry.name)

    for entry in variable_entries:
        ok, msg = run_gh(f"gh variable set {entry.name} --env {env} --body '{entry.value}'")
        if ok:
            result.variables_set.append(entry.name)
        else:
            logger.warning(f"failed to set variable {entry.name} for env {env}: {msg}")
            result.variables_failed.append(entry.name)

    return result


def sync_github(input_model: SyncGithubInput) -> SyncGithubResult:
    work_dir = input_model.settings.work_dir
    config = input_model.config
    env_names = input_model.env_names or [p.name for p in config.envs(work_dir)]
    run_gh = input_model.run_gh or _default_run_gh

    reqs = collect_requirements(config, input_model.provider_hints_registry, input_model.selected_bundles)

    result = SyncGithubResult(dry_run=input_model.dry_run)

    for env in env_names:
        sections = _render_env_workflow(env, config, reqs.secrets, reqs.variables)
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
        secret_entries = resolve_secret_values(reqs.secrets, env_vars)
        variable_entries = resolve_variable_values(reqs.variables, env_vars)
        env_result = sync_env_secrets_and_variables(
            input_model.owner_repo, env, secret_entries, variable_entries, input_model.dry_run, run_gh
        )
        result.env_sync_results.append(env_result)
        logger.info(f"env {env}: secrets={len(env_result.secrets_set)}, variables={len(env_result.variables_set)}")

    return result
