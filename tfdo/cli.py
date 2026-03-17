from ask_shell import console

from tfdo._internal.core import cmd_apply, cmd_check, cmd_destroy, cmd_init, cmd_plan  # noqa: F401
from tfdo._internal.typer_app import app


def typer_main() -> None:
    console.configure_logging(app)
    app()
