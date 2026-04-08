from __future__ import annotations

from pathlib import Path


def resolve_var_files(
    run_dir: Path,
    config_var_files: list[str],
    cli_var_files: list[str],
) -> list[Path]:
    return [(run_dir / f).resolve() for f in [*config_var_files, *cli_var_files]]


def validate_var_files(resolved: list[Path]) -> None:
    missing = [p for p in resolved if not p.is_file()]
    if missing:
        paths = ", ".join(str(p) for p in missing)
        raise FileNotFoundError(f"var files not found: {paths}")


def var_file_flags(resolved: list[Path]) -> list[str]:
    return [f"-var-file={p}" for p in resolved]
