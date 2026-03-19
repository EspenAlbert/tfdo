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
