from __future__ import annotations

import logging
from pathlib import Path
from typing import NamedTuple

import yaml
from ask_shell._internal.interactive import ChoiceTyped, select_list_multiple_choices
from pydantic import BaseModel, ConfigDict, Field
from zero_3rdparty.file_utils import ensure_parents_write_text

from tfdo._internal.boot.s3_bootstrap import check_tf_version, provision_s3_bucket
from tfdo._internal.cache import module_cache
from tfdo._internal.cache.module_cache import UNRESOLVED
from tfdo._internal.config.config_file import CONFIG_FILENAME
from tfdo._internal.config.config_model import ModuleConstraint, ProviderConstraint, S3Backend
from tfdo._internal.config.provider_hints import ModuleHint, ProviderHints, load_provider_hints
from tfdo._internal.models import TfDoBaseInput
from tfdo._internal.new.backend_bootstrap import DEFAULT_KEY_TEMPLATE
from tfdo._internal.settings import TfDoSettings

logger = logging.getLogger(__name__)


class CachedModule(NamedTuple):
    source: str
    version: str


class BackendYaml(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str


_TFDO_GITIGNORE_LINES = [
    ".tfdo/",
    ".terraform/",
    "*.tfstate",
    "*.tfstate.backup",
    ".terraform.tfstate.lock.info",
]


class TfdoBootInput(TfDoBaseInput):
    backend_choice: str = "skip"
    bucket: str | None = None
    region: str | None = None
    providers: list[str] = Field(default_factory=list)
    modules: list[ModuleConstraint] = Field(default_factory=list)


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


def _load_existing_backend(backends_dirs: list[Path], name: str) -> BackendYaml:
    for d in backends_dirs:
        candidate = d / f"{name}.yaml"
        if candidate.is_file():
            return BackendYaml.model_validate(yaml.safe_load(candidate.read_text()) or {})
    raise ValueError(f"Backend '{name}' not found in: {backends_dirs}")


def scan_backend_names(backends_dirs: list[Path]) -> list[str]:
    names = []
    for d in backends_dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.suffix in (".yaml", ".yml"):
                names.append(f.stem)
    return names


def select_modules(providers: list[str], hints_registry: dict[str, ProviderHints]) -> list[ModuleConstraint]:
    result = []
    for provider in providers:
        hints = hints_registry.get(provider)
        if not hints or not hints.modules:
            continue
        choices: list[ChoiceTyped[ModuleHint]] = [
            ChoiceTyped(name=h.alias, value=h, checked=True) for h in hints.modules
        ]
        selected: list[ModuleHint] = select_list_multiple_choices(f"{provider} modules", choices, default=[])
        result.extend(ModuleConstraint(source=h.path) for h in selected)
    return result


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


def boot_repo(input_model: TfdoBootInput) -> TfdoBootResult:
    settings = input_model.settings
    work_dir = settings.work_dir
    config_path = work_dir / CONFIG_FILENAME

    if config_path.is_file():
        raise ValueError(f"tfdo.yaml already exists in {work_dir}. Use 'tfdo new ...' to extend an existing repo.")

    tf_version = check_tf_version(settings.binary)
    raw: dict = {"tf_version": tf_version}

    match input_model.backend_choice:
        case "skip":
            pass
        case "create-new":
            if not input_model.bucket or not input_model.region:
                raise ValueError("bucket and region are required when backend_choice is 'create-new'")
            provision_s3_bucket(input_model.bucket, input_model.region)
            backend = S3Backend(bucket=input_model.bucket, region=input_model.region, key=DEFAULT_KEY_TEMPLATE)
            raw["backend"] = backend.model_dump(mode="json", exclude_none=True)
        case backend_name:
            raw["backend"] = _load_existing_backend(settings.backends_dirs, backend_name).model_dump()

    if input_model.providers:
        raw["providers"] = [ProviderConstraint(name=p).model_dump(exclude_none=True) for p in input_model.providers]

    selected_modules = _resolve_modules(input_model)
    cached, pinned_modules = _populate_module_cache(selected_modules, settings)

    if pinned_modules:
        raw["modules"] = [m.model_dump(exclude_none=True) for m in pinned_modules]

    ensure_parents_write_text(config_path, yaml.dump(raw, default_flow_style=False))
    gitignore_path = _ensure_gitignore_lines(work_dir)

    logger.info("tfdo boot complete! run `tfdo new run-dir` to get started!")

    return TfdoBootResult(
        written_paths=[config_path, gitignore_path],
        terraform_version=tf_version,
        backend_choice=input_model.backend_choice,
        cached_modules=cached,
    )
