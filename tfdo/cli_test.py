from unittest.mock import MagicMock

import pytest

import tfdo.cli as cli_module

_CLI_APP_ATTR = "app"


def test_cli_module_registers_typer_entry() -> None:
    assert callable(cli_module.typer_main)


def test_typer_main_configures_logging_and_invokes_app(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_logging = cli_module.console.configure_logging
    app_mock = MagicMock()
    monkeypatch.setattr(cli_module, _CLI_APP_ATTR, app_mock)
    configure = MagicMock()
    monkeypatch.setattr(cli_module.console, _configure_logging.__name__, configure)
    cli_module.typer_main()
    configure.assert_called_once_with(app_mock)
    app_mock.assert_called_once()
