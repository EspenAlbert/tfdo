import json
import logging
import sys

import typer

from tfdo._internal.schema.diff import (
    DEV_SIDE_TOKEN,
    SchemaDiffInput,
    render_schema_diff_rich,
    resolve_schema_diff_sides,
    schema_diff,
)
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
    no_cache: bool = typer.Option(False, "--no-cache", help="Skip schema cache read and write"),
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
                no_cache=no_cache,
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


@schema_app.command("diff")
def schema_diff_cmd(
    ctx: typer.Context,
    provider: str = typer.Option(..., "--provider", help="required_providers local name (e.g. mongodbatlas)"),
    source: str | None = typer.Option(
        None,
        "--source",
        help="Registry source namespace/type (optional when tfdo has a built-in default for --provider)",
    ),
    from_constraint: str | None = typer.Option(
        None,
        "--from",
        help=f"Version constraint or literal {DEV_SIDE_TOKEN!r}; omit when --to is a version to compare dev plugin to that version",
    ),
    to_constraint: str | None = typer.Option(
        None,
        "--to",
        help=f"Version constraint or literal {DEV_SIDE_TOKEN!r}; omit when --from is a version to compare that version to dev plugin",
    ),
    resource: str | None = typer.Option(
        None,
        "--resource",
        help="Single resource type to diff (same semantics as schema show)",
    ),
    path_parts: list[str] = typer.Option(
        [],
        "--path",
        help="Limit attribute/block detail rows to this path or descendants (repeatable); does not filter resource add/remove lists",
    ),
    no_cache: bool = typer.Option(False, "--no-cache", help="Skip schema cache read and write"),
    as_json: bool = typer.Option(False, "--json", help="Print JSON to stdout"),
) -> None:
    """Compare resource schemas for two version constraints or for registry vs local dev plugin.

    Examples:
        tfdo schema diff --provider mongodbatlas --from 1.18.0 --to 1.19.0
        tfdo schema diff --provider aws --source hashicorp/aws --from 5.0.0 --to 5.1.0 --json
        tfdo schema diff --provider mongodbatlas --from 1.18.0
        tfdo schema diff --provider mongodbatlas --from 1.18.0 --to dev
        tfdo schema diff --provider mongodbatlas --to 1.19.0
        tfdo schema diff --provider mongodbatlas --from 1.18.0 --to 1.19.0 --resource mongodbatlas_cluster --path region
    """
    try:
        left, right = resolve_schema_diff_sides(from_constraint, to_constraint)
        paths = [p.strip() for p in path_parts if p.strip()] or None
        result = schema_diff(
            SchemaDiffInput(
                settings=get_settings(ctx),
                provider=provider,
                source=source,
                left=left,
                right=right,
                no_cache=no_cache,
                attribute_paths=paths,
                resource=resource,
            )
        )
    except (ValueError, RuntimeError) as e:
        logger.error(f"{e}")
        raise typer.Exit(code=1) from e
    if as_json:
        sys.stdout.write(result.to_json())
        return
    render_schema_diff_rich(result)
