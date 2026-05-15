import os
from pathlib import Path

import typer
from ask_shell.settings import AskShellSettings, ShellRunSummary

from tfdo._internal.settings import InteractiveMode, TfDoSettings

app = typer.Typer(
    name="tfdo",
    help="Terraform/OpenTofu lifecycle CLI with multi-directory orchestration, retry, and CI scaffold",
    pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False,
)


@app.callback()
def main_callback(
    ctx: typer.Context,
    binary: str = typer.Option(
        "terraform", "-b", "--binary", envvar="TFDO_BINARY", help="Terraform binary name or path"
    ),
    tf_version: str | None = typer.Option(
        None, "-V", "--tf-version", envvar="TFDO_TF_VERSION", help="Terraform version (uses mise for version selection)"
    ),
    work_dir: Path | None = typer.Option(
        None, "-w", "--work-dir", envvar="TFDO_WORK_DIR", help="Working directory for terraform commands"
    ),
    interactive: InteractiveMode = typer.Option(
        InteractiveMode.AUTO,
        "--interactive",
        envvar="TFDO_INTERACTIVE",
        help="Interactive mode: auto (detect TTY), always (force stdin), never (no stdin)",
    ),
    log_level: str = typer.Option("INFO", "--log-level", help="Log level for tfdo"),
    passthrough: bool = typer.Option(
        False, "--passthrough", help="Disable parsed output, pass raw ANSI from terraform"
    ),
    verbose_shell: bool = typer.Option(
        False, "--verbose-shell", envvar="TFDO_VERBOSE_SHELL", help="Log successful shell command completions"
    ),
) -> None:
    kwargs: dict = dict(
        binary=binary,
        tf_version=tf_version,
        interactive=interactive,
        log_level=log_level,
        passthrough=passthrough,
        verbose_shell=verbose_shell,
    )
    if work_dir is not None:
        kwargs["work_dir"] = work_dir
    settings = TfDoSettings(**kwargs)
    ctx.obj = settings
    os.environ[AskShellSettings.ENV_NAME_SHELL_RUN_SUMMARY] = (
        ShellRunSummary.ALL if settings.verbose_shell else ShellRunSummary.ERRORS_ONLY
    )


def get_settings(ctx: typer.Context) -> TfDoSettings:
    settings: TfDoSettings = ctx.obj
    return settings
