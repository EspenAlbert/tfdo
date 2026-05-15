from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import NamedTuple

from ask_shell._internal.interactive import text
from ask_shell.shell import ShellError, run_and_wait

from tfdo._internal.settings import TfDoSettings

logger = logging.getLogger(__name__)

_GITHUB_ACTIONS_URL = "https://token.actions.githubusercontent.com"
# GitHub's intermediate CA thumbprint required by the AWS OIDC provider API.
# AWS validates certificates directly since 2023, so this value is not
# security-sensitive, but the field remains mandatory. Update if GitHub rotates their CA.
_GITHUB_THUMBPRINT = "6938fd4d98bab03faadb97b34396831e3780aea1"
_ENTITY_ALREADY_EXISTS = "EntityAlreadyExists"


def provision_oidc_provider(account_id: str) -> str:
    expected_arn = f"arn:aws:iam::{account_id}:oidc-provider/token.actions.githubusercontent.com"
    run = run_and_wait("aws iam list-open-id-connect-providers", cwd=Path.cwd())
    data = run.parse_output(dict)
    existing = [p["Arn"] for p in data.get("OpenIDConnectProviderList", [])]
    if expected_arn in existing:
        logger.info(f"OIDC provider already exists: {expected_arn}")
        return expected_arn
    run = run_and_wait(
        f"aws iam create-open-id-connect-provider"
        f" --url {_GITHUB_ACTIONS_URL}"
        f" --client-id-list sts.amazonaws.com"
        f" --thumbprint-list {_GITHUB_THUMBPRINT}",
        cwd=Path.cwd(),
    )
    data = run.parse_output(dict)
    arn = data["OpenIDConnectProviderArn"]
    logger.info(f"Created OIDC provider: {arn}")
    return arn


def provision_oidc_role(account_id: str, org: str, repo: str, env: str, role_name: str, bucket: str) -> str:
    trust_policy = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Federated": f"arn:aws:iam::{account_id}:oidc-provider/token.actions.githubusercontent.com"
                    },
                    "Action": "sts:AssumeRoleWithWebIdentity",
                    "Condition": {
                        "StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"},
                        "StringLike": {
                            "token.actions.githubusercontent.com:sub": f"repo:{org}/{repo}:environment:{env}"
                        },
                    },
                }
            ],
        }
    )
    s3_policy = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                    "Resource": f"arn:aws:s3:::{bucket}/*",
                },
                {
                    "Effect": "Allow",
                    "Action": "s3:ListBucket",
                    "Resource": f"arn:aws:s3:::{bucket}",
                },
            ],
        }
    )
    try:
        run = run_and_wait(
            f"aws iam create-role --role-name {role_name} --assume-role-policy-document '{trust_policy}'",
            cwd=Path.cwd(),
        )
        data = run.parse_output(dict)
        role_arn = data["Role"]["Arn"]
        logger.info(f"Created IAM role: {role_arn}")
    except ShellError as e:
        if _ENTITY_ALREADY_EXISTS not in e.run.stdout_one_line and _ENTITY_ALREADY_EXISTS not in str(e):
            raise
        run = run_and_wait(f"aws iam get-role --role-name {role_name}", cwd=Path.cwd())
        data = run.parse_output(dict)
        role_arn = data["Role"]["Arn"]
        logger.info(f"IAM role already exists: {role_arn}")

    run_and_wait(
        f"aws iam put-role-policy --role-name {role_name} --policy-name tfdo-s3-access --policy-document '{s3_policy}'",
        cwd=Path.cwd(),
    )
    logger.info(f"Attached S3 inline policy to {role_name}")
    return role_arn


class OidcWizardResult(NamedTuple):
    repo_org: str
    repo_name: str
    oidc_roles: dict[str, str]


def run_oidc_wizard(
    settings: TfDoSettings, org: str, repo: str, bucket: str | None = None, backend_bucket: str | None = None
) -> OidcWizardResult:
    work_dir = settings.work_dir
    bucket_default = bucket or backend_bucket or ""
    bucket = bucket or text("S3 bucket name for IAM policy scope", default=bucket_default)

    run = run_and_wait("aws sts get-caller-identity", cwd=work_dir)
    account_id = run.parse_output(dict)["Account"]

    provision_oidc_provider(account_id)

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
