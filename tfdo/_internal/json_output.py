import logging
import sys
from pathlib import Path

import typer
from zero_3rdparty.file_utils import ensure_parents_write_text

logger = logging.getLogger(__name__)


def write_json_cli_output(text: str, *, output: Path | None) -> None:
    if output is not None:
        ensure_parents_write_text(output, text)
        logger.info(f"Wrote JSON to '{output}'")
        return
    sys.stdout.write(text)


def exit_if_output_without_json(*, as_json: bool, output: Path | None, logger: logging.Logger) -> None:
    if output is None or as_json:
        return
    logger.error("--output requires --json")
    raise typer.Exit(code=1)
