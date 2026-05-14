from __future__ import annotations

import logging

import typer
from ask_shell._internal.interactive import ChoiceTyped, select_list, select_list_multiple_choices, text

from tfdo._internal.boot.boot_repo import TfdoBootInput, boot_repo, scan_backend_names
from tfdo._internal.config.provider_hints import load_provider_hints
from tfdo._internal.typer_app import app, get_settings

logger = logging.getLogger(__name__)


@app.command("boot")
def boot_cmd(
    ctx: typer.Context,
    oidc: bool = typer.Option(False, "--oidc/--no-oidc", help="Provision GitHub OIDC provider and per-env IAM roles"),
) -> None:
    """Bootstrap a new tfdo-managed Terraform repo."""
    settings = get_settings(ctx)
    backend_choice = "skip"
    bucket: str | None = None
    region: str | None = None
    providers: list[str] = []

    if settings.is_interactive:
        backend_names = scan_backend_names(settings.backends_dirs)
        backend_choice = select_list(
            "Select backend:",
            backend_names + ["create-new", "skip"],
            default="skip",
        )
        if backend_choice == "create-new":
            bucket = text("S3 bucket name")
            region = text("AWS region", default="us-east-1")

        hints = load_provider_hints(settings.resolved_provider_hints_path)
        provider_choices = [ChoiceTyped(name=p, value=p, checked=False) for p in hints]
        if provider_choices:
            providers = select_list_multiple_choices(
                "Select providers (space to toggle, enter to confirm):",
                provider_choices,
                default=[],
            )

    result = boot_repo(
        TfdoBootInput(
            settings=settings,
            backend_choice=backend_choice,
            bucket=bucket,
            region=region,
            providers=providers,
            oidc=oidc,
        )
    )
    logger.info(f"Written: {', '.join(str(p) for p in result.written_paths)}")
