import logging

import typer

import tfdo
from tfdo._internal.settings import TfDoSettings, load_user_config
from tfdo._internal.typer_app import app, get_settings

logger = logging.getLogger(__name__)


def _print_info(settings: TfDoSettings) -> None:
    user_config = load_user_config(settings)
    lines = [
        f"tfdo {tfdo.VERSION}",
        "",
        "Settings:",
        f"  binary:      {settings.binary}",
        f"  tf_version:  {settings.tf_version or '(not set)'}",
        f"  work_dir:    {settings.work_dir}",
        f"  interactive: {settings.interactive}",
        f"  passthrough: {settings.passthrough}",
        f"  log_level:   {settings.log_level}",
        "",
        "Paths:",
        f"  user_config: {settings.user_config_path}",
        f"  static_root: {settings.static_root}",
        f"  cache_root:  {settings.cache_root}",
        "",
        "User config:",
    ]
    if user_config.check:
        lines.append(f"  check.tflint: {user_config.check.tflint}")
    else:
        lines.append("  (no user config found)")
    logger.info("\n".join(lines))


@app.command("info")
def info_cmd(ctx: typer.Context) -> None:
    """Show resolved settings, paths, and user config."""
    settings = get_settings(ctx)
    _print_info(settings)
