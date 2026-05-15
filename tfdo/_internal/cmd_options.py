from collections.abc import Sequence
from pathlib import Path

import typer

from tfdo._internal.models import InitMode


def var_file_option() -> Path | None:
    return typer.Option(None, "--var-file", "-f", help="Path to a terraform .tfvars file")


def auto_approve_option() -> bool:
    return typer.Option(False, "--auto-approve", help="Skip interactive approval prompts")


def init_mode_option() -> InitMode:
    return typer.Option(
        InitMode.AUTO,
        "--init-mode",
        "-I",
        envvar="TFDO_INIT_MODE",
        help="Init behavior: auto (run init on error related to init), always (run init first), never (skip init)",
    )


def include_option() -> list[str]:
    return typer.Option([], "--include", help="Glob patterns: only matching directories are checked")


def exclude_option(
    *,
    default_patterns: Sequence[str] | None = None,
    help_text: str = "Glob patterns: matching directories are skipped",
) -> list[str]:
    defaults = list(default_patterns) if default_patterns else []
    return typer.Option(
        defaults,
        "--exclude",
        help=help_text,
    )


def tflint_option() -> bool | None:
    return typer.Option(
        None, "--tflint/--no-tflint", envvar="TFDO_TFLINT", help="Run tflint linter alongside fmt+validate"
    )


def skip_check_providers_option() -> bool | None:
    return typer.Option(
        None,
        "--skip-check-providers/--no-skip-check-providers",
        envvar="TFDO_SKIP_CHECK_PROVIDERS",
        help="Skip provider declaration and credential checks",
    )
