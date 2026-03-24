from typer.testing import CliRunner

from tfdo._internal.check import cmd_check  # noqa: F401
from tfdo._internal.core import cmd_apply, cmd_destroy, cmd_info, cmd_init, cmd_plan  # noqa: F401
from tfdo._internal.inspect import cmd_inspect  # noqa: F401
from tfdo._internal.schema import cmd_schema  # noqa: F401
from tfdo._internal.typer_app import app

runner = CliRunner()

EXPECTED_COMMANDS = {"init", "i", "plan", "p", "apply", "a", "destroy", "d", "check", "c", "info", "inspect", "schema"}


def test_help_shows_all_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    registered = {cmd.name for cmd in app.registered_commands if cmd.name}
    group_names = {g.name for g in app.registered_groups}
    assert registered | group_names == EXPECTED_COMMANDS


def test_alias_invokes_same_command():
    result_full = runner.invoke(app, ["init", "--help"])
    result_alias = runner.invoke(app, ["i", "--help"])
    assert result_full.exit_code == 0
    assert result_alias.exit_code == 0
    assert "terraform init" in result_full.output.lower()
    assert "terraform init" in result_alias.output.lower()
