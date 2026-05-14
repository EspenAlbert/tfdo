from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, NamedTuple

import yaml
from ask_shell._internal.interactive import ChoiceTyped, select_list, select_list_multiple_choices, text
from ask_shell.shell import run_and_wait
from pydantic import BaseModel, Field, TypeAdapter
from zero_3rdparty.file_utils import ensure_parents_write_text

from tfdo._internal.boot.oidc_bootstrap import provision_oidc_provider, provision_oidc_role
from tfdo._internal.boot.s3_bootstrap import check_tf_version, provision_s3_bucket
from tfdo._internal.cache import module_cache
from tfdo._internal.cache.module_cache import UNRESOLVED
from tfdo._internal.config.config_file import CONFIG_FILENAME
from tfdo._internal.config.config_model import (
    BackendConfig,
    CiConfig,
    ModuleConstraint,
    ProviderConstraint,
    S3Backend,
    TfDoConfig,
)
from tfdo._internal.config.provider_hints import ProviderHints, available_module_choices, load_provider_hints
from tfdo._internal.git_utils import parse_git_remote
from tfdo._internal.models import TfDoBaseInput
from tfdo._internal.new.backend_bootstrap import DEFAULT_KEY_TEMPLATE
from tfdo._internal.settings import TfDoSettings

logger = logging.getLogger(__name__)

_BACKEND_ADAPTER: TypeAdapter[BackendConfig] = TypeAdapter(Annotated[BackendConfig, Field(discriminator="type")])


class CachedModule(NamedTuple):
    source: str
    version: str


class OidcWizardResult(NamedTuple):
    repo_org: str
    repo_name: str
    oidc_roles: dict[str, str]


_TFDO_GITIGNORE_LINES = [
    ".tfdo/",
    ".terraform/",
    "*.tfstate",
    "*.tfstate.backup",
    ".terraform.tfstate.lock.info",
    f"*{TfDoSettings.DEP_TFVARS_SUFFIX}",
]


class TfdoBootInput(TfDoBaseInput):
    backend_choice: str = "skip"
    bucket: str | None = None
    region: str | None = None
    providers: list[str] = Field(default_factory=list)
    modules: list[ModuleConstraint] = Field(default_factory=list)
    oidc: bool = False


class TfdoBootResult(BaseModel):
    written_paths: list[Path] = Field(default_factory=list)
    terraform_version: str
    backend_choice: str
    cached_modules: list[CachedModule] = Field(default_factory=list)


def _ensure_gitignore_lines(work_dir: Path) -> Path:
    gitignore = work_dir / ".gitignore"
    existing = gitignore.read_text() if gitignore.is_file() else ""
    existing_lines = set(existing.splitlines())
    missing = [line for line in _TFDO_GITIGNORE_LINES if line not in existing_lines]
    if missing:
        updated = existing.rstrip("\n") + "\n" + "\n".join(missing) + "\n"
        ensure_parents_write_text(gitignore, updated)
    return gitignore


def _load_existing_backend(backends_dirs: list[Path], name: str) -> BackendConfig:
    for d in backends_dirs:
        candidate = d / f"{name}.yaml"
        if candidate.is_file():
            return _BACKEND_ADAPTER.validate_python(yaml.safe_load(candidate.read_text()) or {})
    raise ValueError(f"Backend '{name}' not found in: {backends_dirs}")


def _save_backend_to_user_dir(settings: TfDoSettings, bucket: str, backend: S3Backend) -> None:
    """Persist the backend as a named YAML file so future boots can reference it."""
    backends_dir = settings.backends_dirs[0] if settings.backends_dirs else None
    if backends_dir is None:
        return
    backend_data = backend.model_dump(mode="json", exclude_none=True)
    ensure_parents_write_text(backends_dir / f"{bucket}.yaml", yaml.dump(backend_data, default_flow_style=False))
    logger.info(f"saved backend '{bucket}' to {backends_dir}")


def scan_backend_names(backends_dirs: list[Path]) -> list[str]:
    names = []
    for d in backends_dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.suffix in (".yaml", ".yml"):
                names.append(f.stem)
    return names


@contextmanager
def _config_session(config_path: Path, binary: str) -> Iterator[TfDoConfig]:
    """Load or create config; yield for mutation; dump to disk on exit even on error."""
    if config_path.is_file():
        config = TfDoConfig.model_validate(yaml.safe_load(config_path.read_text()) or {})
        config.tf_version = config.tf_version or check_tf_version(binary)
    else:
        config = TfDoConfig(tf_version=check_tf_version(binary))
    try:
        yield config
    finally:
        data = config.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
        ensure_parents_write_text(config_path, yaml.dump(data, default_flow_style=False))


def select_modules(providers: list[str], hints_registry: dict[str, ProviderHints]) -> list[ModuleConstraint]:
    choices = available_module_choices(providers, hints_registry, checked=True)
    if not choices:
        return []
    selected = select_list_multiple_choices("Select modules:", choices, default=[])
    return [ModuleConstraint(source=mc.hint.source) for mc in selected]


def _resolve_modules(input_model: TfdoBootInput) -> list[ModuleConstraint]:
    if input_model.modules:
        return input_model.modules
    settings = input_model.settings
    if not input_model.providers or not settings.is_interactive:
        return []
    hints_registry = load_provider_hints(settings.resolved_provider_hints_path)
    return select_modules(input_model.providers, hints_registry)


def _populate_module_cache(
    modules: list[ModuleConstraint], settings: TfDoSettings
) -> tuple[list[CachedModule], list[ModuleConstraint]]:
    """Populate the shared module cache and return resolved (cached, pinned) pairs.

    For modules without a constraint, terraform resolves the latest version.
    The resolved version is written back to ``tfdo.yaml`` via the returned
    ``pinned`` list so the project is reproducible after the first boot.
    """
    cached: list[CachedModule] = []
    pinned: list[ModuleConstraint] = []
    for m in modules:
        request_version = m.constraint or UNRESOLVED
        hit = module_cache.lookup(settings.cache_root, m.source, request_version)
        target = (
            hit if hit is not None else module_cache.populate(settings.cache_root, m.source, request_version, settings)
        )
        resolved_version = target.name
        cached.append(CachedModule(source=m.source, version=resolved_version))
        pinned.append(ModuleConstraint(source=m.source, constraint=resolved_version))
    return cached, pinned


def _run_oidc_wizard(input_model: TfdoBootInput, backend_bucket: str | None = None) -> OidcWizardResult:
    settings = input_model.settings
    work_dir = settings.work_dir
    bucket_default = input_model.bucket or backend_bucket or ""
    bucket = input_model.bucket or text("S3 bucket name for IAM policy scope", default=bucket_default)

    run = run_and_wait("aws sts get-caller-identity", cwd=work_dir)
    account_id = run.parse_output(dict)["Account"]

    provision_oidc_provider(account_id)

    remote = parse_git_remote(work_dir)
    org = text("GitHub org", default=remote.org if remote else "")
    repo = text("GitHub repo", default=remote.repo if remote else "")

    envs_dir = work_dir / "envs"
    env_names = sorted(d.name for d in envs_dir.iterdir() if d.is_dir()) if envs_dir.is_dir() else []
    if not env_names:
        logger.info("No envs found under envs/; skipping IAM role provisioning")
        return OidcWizardResult(repo_org=org, repo_name=repo, oidc_roles={})

    oidc_roles: dict[str, str] = {}
    for env in env_names:
        role_name = text(f"IAM role name for env '{env}'", default=f"tfdo-{repo}-{env}")
        oidc_roles[env] = provision_oidc_role(account_id, org, repo, env, role_name, bucket)
    return OidcWizardResult(repo_org=org, repo_name=repo, oidc_roles=oidc_roles)


def _run_scaffold_wizard(input_model: TfdoBootInput, config: TfDoConfig) -> TfdoBootInput:
    """Prompt for backend and providers interactively, using existing config as defaults."""
    settings = input_model.settings
    backend_names = scan_backend_names(settings.backends_dirs)
    match config.backend:
        case S3Backend(bucket=existing_bucket, region=existing_region):
            default_backend = existing_bucket if existing_bucket in backend_names else "skip"
        case _:
            existing_bucket, existing_region = None, None
            default_backend = "skip"
    existing_provider_names = {p.name for p in config.providers}

    backend_choice = select_list(
        "Select backend:",
        backend_names + ["create-new", "skip"],
        default=default_backend,
    )
    bucket = input_model.bucket
    region = input_model.region
    if backend_choice == "create-new":
        bucket = text("S3 bucket name", default=existing_bucket or "")
        region = text("AWS region", default=existing_region or "us-east-1")

    hints = load_provider_hints(settings.resolved_provider_hints_path)
    providers: list[str] = []
    provider_choices = [ChoiceTyped(name=p, value=p, checked=p in existing_provider_names) for p in hints]
    if provider_choices:
        providers = select_list_multiple_choices(
            "Select providers (space to toggle, enter to confirm):",
            provider_choices,
            default=[],
        )

    modules = select_modules(providers, hints)

    return input_model.model_copy(
        update={
            "backend_choice": backend_choice,
            "bucket": bucket,
            "region": region,
            "providers": providers,
            "modules": modules,
        }
    )


def _apply_scaffold(input_model: TfdoBootInput, config: TfDoConfig) -> tuple[TfdoBootInput, list[CachedModule]]:
    settings = input_model.settings
    if settings.is_interactive and input_model.backend_choice == "skip" and not input_model.providers:
        input_model = _run_scaffold_wizard(input_model, config)

    match input_model.backend_choice:
        case "skip":
            pass
        case "create-new":
            if not input_model.bucket or not input_model.region:
                raise ValueError("bucket and region are required when backend_choice is 'create-new'")
            provision_s3_bucket(input_model.bucket, input_model.region)
            backend = S3Backend(bucket=input_model.bucket, region=input_model.region, key=DEFAULT_KEY_TEMPLATE)
            config.backend = backend
            _save_backend_to_user_dir(settings, input_model.bucket, backend)
        case backend_name:
            config.backend = _load_existing_backend(settings.backends_dirs, backend_name)

    if input_model.providers:
        config.providers = [ProviderConstraint(name=p) for p in input_model.providers]

    selected_modules = _resolve_modules(input_model)
    _, pinned_modules = _populate_module_cache(selected_modules, settings)
    cached = [CachedModule(source=m.source, version=m.constraint or "") for m in pinned_modules]

    if pinned_modules:
        config.modules = pinned_modules

    return input_model, cached


def boot_repo(input_model: TfdoBootInput) -> TfdoBootResult:
    settings = input_model.settings
    config_path = settings.work_dir / CONFIG_FILENAME

    with _config_session(config_path, settings.binary) as config:
        input_model, cached = _apply_scaffold(input_model, config)

        if input_model.oidc:
            match config.backend:
                case S3Backend(bucket=backend_bucket):
                    pass
                case _:
                    backend_bucket = None
            oidc_result = _run_oidc_wizard(input_model, backend_bucket=backend_bucket)
            ci = config.ci or CiConfig()
            ci.oidc = True
            ci.repo_org = oidc_result.repo_org
            ci.repo_name = oidc_result.repo_name
            if oidc_result.oidc_roles:
                ci.oidc_roles = oidc_result.oidc_roles
            config.ci = ci

    gitignore_path = _ensure_gitignore_lines(settings.work_dir)
    logger.info("tfdo boot complete! run `tfdo new run-dir` to get started!")

    return TfdoBootResult(
        written_paths=[config_path, gitignore_path],
        terraform_version=config.tf_version or "",
        backend_choice=input_model.backend_choice,
        cached_modules=cached,
    )
