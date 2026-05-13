from __future__ import annotations

import logging
from pathlib import Path

from ask_shell.shell import ShellError, run_and_wait

logger = logging.getLogger(__name__)

_MIN_TF_VERSION = (1, 10)
_BUCKET_ALREADY_OWNED = "BucketAlreadyOwnedByYou"


def check_tf_version(binary: str) -> str:
    run = run_and_wait(f"{binary} version -json", cwd=Path.cwd())
    data = run.parse_output(dict)
    version_str = next((v for k, v in data.items() if k.endswith("_version") and isinstance(v, str)), "")
    parts = version_str.lstrip("v").split(".")
    major, minor = int(parts[0]), int(parts[1])
    if (major, minor) < _MIN_TF_VERSION:
        raise ValueError(
            f"{binary} version {version_str} is too old; "
            f"requires >= {_MIN_TF_VERSION[0]}.{_MIN_TF_VERSION[1]} for native S3 locking"
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
