import logging

import typer

from tfdo._internal.core import executor
from tfdo._internal.models import InitInput
from tfdo._internal.typer_app import app, get_settings

logger = logging.getLogger(__name__)


@app.command("init")
@app.command("i")
def init_cmd(
    ctx: typer.Context,
    extra_args: list[str] = typer.Argument(default=None, help="Extra arguments forwarded to terraform init"),
) -> None:
    """Run terraform init with retry on transient errors."""
    settings = get_settings(ctx)
    input_model = InitInput(settings=settings, extra_args=extra_args or [])
    result = executor.init(input_model)
    logger.info(f"init complete: exit_code={result.exit_code} attempts={result.attempts_used}")
    raise typer.Exit(result.exit_code)
