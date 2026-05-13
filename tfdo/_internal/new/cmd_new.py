from __future__ import annotations

import logging

import typer

from tfdo._internal.new.backend_bootstrap import NewBackendInput, new_backend
from tfdo._internal.typer_app import app, get_settings

logger = logging.getLogger(__name__)

new_app = typer.Typer(help="Provision new tfdo-managed infrastructure")
app.add_typer(new_app, name="new")


@new_app.command("backend")
def backend_cmd(
    ctx: typer.Context,
    bucket: str = typer.Option(..., "--bucket", "-b", help="S3 bucket name for Terraform state"),
    region: str = typer.Option("us-east-1", "--region", "-r", help="AWS region"),
    key: str = typer.Option(
        "{path}/terraform.tfstate", "--key", help="State key template; {path} is resolved per run-dir"
    ),
) -> None:
    """Write backend.tf to all run-dirs."""
    settings = get_settings(ctx)
    result = new_backend(NewBackendInput(settings=settings, bucket=bucket, region=region, key=key))
    logger.info(f"tfdo.yaml updated: {result.updated_yaml}")
    logger.info(f"backend.tf written to {len(result.backend_tf_files)} run-dir(s):")
    for f in result.backend_tf_files:
        logger.info(f"  {f}")
