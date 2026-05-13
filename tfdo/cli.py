from ask_shell import console

from tfdo._internal.boot import cmd_boot as _cmd_boot  # noqa: F401
from tfdo._internal.check import cmd_check  # noqa: F401
from tfdo._internal.config import cmd_config  # noqa: F401
from tfdo._internal.core import cmd_apply, cmd_destroy, cmd_info, cmd_init, cmd_plan  # noqa: F401
from tfdo._internal.inspect import cmd_inspect  # noqa: F401
from tfdo._internal.new import cmd_new  # noqa: F401
from tfdo._internal.run import cmd_run  # noqa: F401
from tfdo._internal.schema import cmd_schema  # noqa: F401
from tfdo._internal.typer_app import app


def typer_main() -> None:
    console.configure_logging(app)
    app()
