import logging
import sys
from pathlib import Path

import typer

from tfdo._internal import cmd_options
from tfdo._internal.inspect.inspect_paths_logic import InspectHclPathsInput, inspect_hcl_paths
from tfdo._internal.inspect.resource_usage_logic import ResourceUsageInput, inspect_resource_usage
from tfdo._internal.inspect.schema_input_classify_logic import SchemaInputClassifyMode
from tfdo._internal.typer_app import app, get_settings

logger = logging.getLogger(__name__)

inspect_app = typer.Typer(help="Static inspection of Terraform configuration")
app.add_typer(inspect_app, name="inspect")


@inspect_app.command("hcl-paths")
def inspect_hcl_paths_cmd(
    path: Path = typer.Option(Path.cwd(), "--path", "-p", help="Root directory to scan for Terraform files"),
    as_json: bool = typer.Option(False, "--json", help="Print JSON to stdout"),
) -> None:
    result = inspect_hcl_paths(InspectHclPathsInput(root=path))
    if as_json:
        sys.stdout.write(f"{result.to_canonical_json()}\n")
        return
    for row in result.rows:
        logger.info(f"{row.file} {row.address}:")
        for p in row.attribute_paths:
            logger.info(f"  {p}")
    for err in result.errors:
        logger.warning(f"parse error {err.path}: {err.message}")


@inspect_app.command("resource-usage")
def inspect_resource_usage_cmd(
    ctx: typer.Context,
    path: Path = typer.Option(Path.cwd(), "--path", "-p", help="Root directory to scan for Terraform files"),
    mode: str = typer.Option("all", "--mode", help="included | excluded | all"),
    input_only: bool = typer.Option(
        True,
        "--input-only/--no-input-only",
        help="Input paths only in v1 (default: on)",
    ),
    provider: str = typer.Option(..., "--provider", help="required_providers local name (e.g. mongodbatlas)"),
    source: str | None = typer.Option(
        None,
        "--source",
        help="Registry source namespace/type (optional when tfdo has a built-in default for --provider)",
    ),
    version: str = typer.Option(">= 1.0", "--version", help="required_providers version constraint"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Skip schema cache read and write"),
    include: list[str] = cmd_options.include_option(),
    exclude: list[str] = cmd_options.exclude_option(
        default_patterns=(".github/*", "tests/*"),
        help_text="Glob patterns: matching directories are skipped (default .github/* and tests/*; any --exclude replaces defaults)",
    ),
) -> None:
    try:
        mode_e = SchemaInputClassifyMode(mode.lower())
    except ValueError:
        logger.error("Invalid --mode; use included, excluded, or all")
        raise typer.Exit(code=1)
    try:
        result = inspect_resource_usage(
            ResourceUsageInput(
                settings=get_settings(ctx),
                root=path,
                mode=mode_e,
                input_only=input_only,
                provider=provider,
                source=source,
                version=version,
                no_cache=no_cache,
                include_patterns=include,
                exclude_patterns=exclude,
            )
        )
    except (ValueError, RuntimeError) as e:
        logger.error(f"{e}")
        raise typer.Exit(code=1) from e
    sys.stdout.write(f"{result.to_canonical_json(error_paths_relative_to=path)}\n")
