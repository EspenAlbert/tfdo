from pathlib import Path

import typer


def var_file_option() -> Path | None:
    return typer.Option(None, "--var-file", "-f", help="Path to a terraform .tfvars file")


def auto_approve_option() -> bool:
    return typer.Option(False, "--auto-approve", help="Skip interactive approval prompts")


def init_first_option() -> bool:
    return typer.Option(False, "--init", help="Run terraform init before the command")
