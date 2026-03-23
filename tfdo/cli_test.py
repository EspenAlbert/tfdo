from unittest.mock import MagicMock

import pytest


def test_cli_module_registers_typer_entry() -> None:
    import tfdo.cli as cli_module

    assert callable(cli_module.typer_main)


def test_typer_main_configures_logging_and_invokes_app(monkeypatch: pytest.MonkeyPatch) -> None:
    import tfdo.cli as cli_module

    app_mock = MagicMock()
    monkeypatch.setattr(cli_module, "app", app_mock)
    configure = MagicMock()
    monkeypatch.setattr(cli_module.console, "configure_logging", configure)
    cli_module.typer_main()
    configure.assert_called_once_with(app_mock)
    app_mock.assert_called_once()
