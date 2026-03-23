import logging
import sys
from pathlib import Path

import typer

from tfdo._internal.inspect.inspect_paths_logic import InspectHclPathsInput, inspect_hcl_paths
from tfdo._internal.typer_app import app

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
