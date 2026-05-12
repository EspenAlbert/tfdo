from __future__ import annotations

import logging
from pathlib import Path

import yaml
from ask_shell.shell import ShellError, run_and_wait
from pydantic import BaseModel, Field
from zero_3rdparty.file_utils import ensure_parents_write_text, find_repo_root

from tfdo._internal import hcl_roundtrip
from tfdo._internal.config.backend_resolution import resolve_placeholders
from tfdo._internal.config.config_file import CONFIG_FILENAME, load_config
from tfdo._internal.config.config_model import S3Backend
from tfdo._internal.core import binary as binary_module
from tfdo._internal.models import TfDoBaseInput
from tfdo._internal.run.discovery import DiscoveredRunDir, discover_run_dirs, parse_discovery_pattern
from tfdo._internal.run.run_context import RunDirContext

logger = logging.getLogger(__name__)

_MIN_TF_VERSION = (1, 10)
_DEFAULT_KEY_TEMPLATE = "{path}/terraform.tfstate"
_BUCKET_ALREADY_OWNED = "BucketAlreadyOwnedByYou"
_BACKEND_TF_FILENAME = "backend.tf"


class NewBackendInput(TfDoBaseInput):
    bucket: str
    region: str
    key: str = _DEFAULT_KEY_TEMPLATE
    encrypt: bool = True


class NewBackendResult(BaseModel):
    bucket: str
    region: str
    updated_yaml: Path
    backend_tf_files: list[Path] = Field(default_factory=list)


def check_tf_version(binary: str) -> str:
    run = run_and_wait(f"{binary} version -json", cwd=Path.cwd())
    data = run.parse_output(dict)
    version_str = next((v for k, v in data.items() if k.endswith("_version") and isinstance(v, str)), "")
    parts = version_str.lstrip("v").split(".")
    major, minor = int(parts[0]), int(parts[1])
    if (major, minor) < _MIN_TF_VERSION:
        raise ValueError(
            f"{binary} version {version_str} is too old; "
            f"tfdo new backend requires >= {_MIN_TF_VERSION[0]}.{_MIN_TF_VERSION[1]} for native S3 locking"
        )
    return version_str


def provision_s3_bucket(bucket: str, region: str) -> None:
    create_cmd = f"aws s3api create-bucket --bucket {bucket} --region {region}"
    if region != "us-east-1":
        create_cmd += f" --create-bucket-configuration LocationConstraint={region}"
    try:
        run_and_wait(create_cmd, cwd=Path.cwd())
        logger.info(f"create-bucket {bucket} ✓")
    except ShellError as e:
        if _BUCKET_ALREADY_OWNED not in e.run.stdout_one_line and _BUCKET_ALREADY_OWNED not in str(e):
            raise
        logger.info(f"bucket {bucket} already exists, skipping creation")

    run_and_wait(
        f"aws s3api put-bucket-versioning --bucket {bucket} --versioning-configuration Status=Enabled",
        cwd=Path.cwd(),
    )
    logger.info(f"put-bucket-versioning {bucket} ✓")

    run_and_wait(
        f"aws s3api put-bucket-encryption --bucket {bucket} "
        '--server-side-encryption-configuration \'{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}\'',
        cwd=Path.cwd(),
    )
    logger.info(f"put-bucket-encryption {bucket} ✓")

    run_and_wait(
        f"aws s3api put-public-access-block --bucket {bucket} "
        "--public-access-block-configuration "
        "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true",
        cwd=Path.cwd(),
    )
    logger.info(f"put-public-access-block {bucket} ✓")


def update_tfdo_yaml_backend(repo_root: Path, backend: S3Backend) -> Path:
    config_path = repo_root / CONFIG_FILENAME
    raw: dict = {}
    if config_path.is_file():
        raw = yaml.safe_load(config_path.read_text()) or {}
    raw["backend"] = backend.model_dump(mode="json", exclude_none=True)
    ensure_parents_write_text(config_path, yaml.dump(raw, default_flow_style=False))
    return config_path


def _backend_tf_for_run_dir(run_dir: Path, rel_path: str, backend: S3Backend) -> None:
    ctx = RunDirContext(name=rel_path.rsplit("/", 1)[-1], path=rel_path, repo_owner="", repo_name="")
    resolved_key = resolve_placeholders(backend.key, ctx)
    resolved_backend = backend.model_copy(update={"key": resolved_key})

    backend_tf = run_dir / _BACKEND_TF_FILENAME
    original = backend_tf.read_text() if backend_tf.is_file() else ""
    updated = hcl_roundtrip.add_backend_block(original, "s3", resolved_backend.hcl_config)
    ensure_parents_write_text(backend_tf, updated)


def write_backend_tf_files(repo_root: Path, backend: S3Backend) -> list[Path]:
    root_config = load_config(repo_root)
    if root_config is None or not root_config.run_dir_discovery:
        logger.warning("no run_dir_discovery pattern in tfdo.yaml; skipping backend.tf generation")
        return []

    pattern = parse_discovery_pattern(root_config.run_dir_discovery)
    run_dirs: list[DiscoveredRunDir] = discover_run_dirs(repo_root, pattern, require_backend=False)
    written: list[Path] = []
    for rd in run_dirs:
        _backend_tf_for_run_dir(rd.path, rd.relative_path, backend)
        written.append(rd.path / _BACKEND_TF_FILENAME)
        logger.info(f"backend.tf written: {rd.relative_path}")
    return written


def new_backend(input_model: NewBackendInput) -> NewBackendResult:
    resolved_binary = binary_module.resolve_binary(input_model.settings)
    check_tf_version(resolved_binary)

    if not input_model.dry_run:
        provision_s3_bucket(input_model.bucket, input_model.region)

    backend = S3Backend(
        bucket=input_model.bucket,
        key=input_model.key,
        region=input_model.region,
        encrypt=input_model.encrypt,
    )

    repo_root = find_repo_root(input_model.settings.work_dir)
    updated_yaml = update_tfdo_yaml_backend(repo_root, backend)
    backend_files = write_backend_tf_files(repo_root, backend)

    return NewBackendResult(
        bucket=input_model.bucket,
        region=input_model.region,
        updated_yaml=updated_yaml,
        backend_tf_files=backend_files,
    )
