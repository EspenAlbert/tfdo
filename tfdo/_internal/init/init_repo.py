from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from zero_3rdparty.file_utils import ensure_parents_write_text

from tfdo._internal.config.config_file import CONFIG_FILENAME
from tfdo._internal.config.config_model import ProviderConstraint
from tfdo._internal.init.s3_bootstrap import check_tf_version, provision_s3_bucket
from tfdo._internal.models import TfDoBaseInput

logger = logging.getLogger(__name__)

_TFDO_GITIGNORE_LINES = [
    ".tfdo/",
    ".terraform/",
    ".terraform.lock.hcl",
    "*.tfstate",
    "*.tfstate.backup",
    ".terraform.tfstate.lock.info",
]


class TfdoInitInput(TfDoBaseInput):
    backend_choice: str = "skip"
    bucket: str | None = None
    region: str | None = None
    providers: list[str] = Field(default_factory=list)


class TfdoInitResult(BaseModel):
    written_paths: list[Path] = Field(default_factory=list)
    terraform_version: str
    backend_choice: str


def _ensure_gitignore_lines(work_dir: Path) -> Path:
    gitignore = work_dir / ".gitignore"
    existing = gitignore.read_text() if gitignore.is_file() else ""
    existing_lines = set(existing.splitlines())
    missing = [line for line in _TFDO_GITIGNORE_LINES if line not in existing_lines]
    if missing:
        updated = existing.rstrip("\n") + "\n" + "\n".join(missing) + "\n"
        ensure_parents_write_text(gitignore, updated)
    return gitignore


def _load_existing_backend(backends_dirs: list[Path], name: str) -> dict:
    for d in backends_dirs:
        candidate = d / f"{name}.yaml"
        if candidate.is_file():
            return yaml.safe_load(candidate.read_text()) or {}
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


def init_repo(input_model: TfdoInitInput) -> TfdoInitResult:
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
            raw["backend"] = {
                "type": "s3",
                "bucket": input_model.bucket,
                "region": input_model.region,
                "key": "{path}/terraform.tfstate",
            }
        case backend_name:
            raw["backend"] = _load_existing_backend(settings.backends_dirs, backend_name)

    if input_model.providers:
        raw["providers"] = [ProviderConstraint(name=p).model_dump(exclude_none=True) for p in input_model.providers]

    ensure_parents_write_text(config_path, yaml.dump(raw, default_flow_style=False))
    gitignore_path = _ensure_gitignore_lines(work_dir)

    logger.info("tfdo init complete! Run 'tfdo new run-dir' to get started.")

    return TfdoInitResult(
        written_paths=[config_path, gitignore_path],
        terraform_version=tf_version,
        backend_choice=input_model.backend_choice,
    )
