from pathlib import Path

import typer

from tfdo._internal.settings import TfDoSettings

app = typer.Typer(
    name="tfdo",
    help="Terraform/OpenTofu lifecycle CLI with retry, workspaces, and CI scaffold",
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
    log_level: str = typer.Option("INFO", "--log-level", help="Log level for tfdo"),
    passthrough: bool = typer.Option(
        False, "--passthrough", help="Disable parsed output, pass raw ANSI from terraform"
    ),
) -> None:
    kwargs: dict = dict(binary=binary, tf_version=tf_version, log_level=log_level, passthrough=passthrough)
    if work_dir is not None:
        kwargs["work_dir"] = work_dir
    ctx.obj = TfDoSettings(**kwargs)


def get_settings(ctx: typer.Context) -> TfDoSettings:
    settings: TfDoSettings = ctx.obj
    return settings
