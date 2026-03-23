import json
import logging
import sys

import typer

from tfdo._internal.schema.inspect_logic import SchemaShowInput, schema_show
from tfdo._internal.typer_app import app, get_settings

logger = logging.getLogger(__name__)

schema_app = typer.Typer(help="Provider schema inspection")
app.add_typer(schema_app, name="schema")


@schema_app.command("show")
def schema_show_cmd(
    ctx: typer.Context,
    provider: str = typer.Option(..., "--provider", help="required_providers local name (e.g. mongodbatlas)"),
    source: str | None = typer.Option(
        None,
        "--source",
        help="Registry source namespace/type (optional when tfdo has a built-in default for --provider)",
    ),
    version: str = typer.Option(">= 1.0", "--version", help="required_providers version constraint"),
    resource: str | None = typer.Option(None, "--resource", help="Resource type; omit to list types for the provider"),
    as_json: bool = typer.Option(False, "--json", help="Print JSON to stdout"),
) -> None:
    try:
        result = schema_show(
            SchemaShowInput(
                settings=get_settings(ctx),
                provider=provider,
                source=source,
                version=version,
                resource=resource,
            )
        )
    except (ValueError, RuntimeError) as e:
        logger.error(f"{e}")
        raise typer.Exit(code=1) from e
    if as_json:
        sys.stdout.write(f"{result.to_canonical_json()}\n")
        return
    if result.resource is None:
        logger.info(f"{len(result.resource_names)} resource type(s)")
        for name in result.resource_names:
            logger.info(name)
        return
    dumped = json.dumps(
        result.resource.model_dump(mode="json", exclude_none=True),
        indent=2,
        sort_keys=True,
    )
    sys.stdout.write(f"{dumped}\n")
