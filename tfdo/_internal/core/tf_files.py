from collections.abc import Iterator
from fnmatch import fnmatch
from pathlib import Path

TERRAFORM_DIR = ".terraform"


def find_tf_directories(
    root: Path,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> list[Path]:
    dirs: list[Path] = []
    for path in root.rglob("*.tf"):
        if TERRAFORM_DIR in path.parts:
            continue
        parent = path.parent
        if parent in dirs:
            continue
        rel = str(parent.relative_to(root))
        if include_patterns and not any(fnmatch(rel, p) for p in include_patterns):
            continue
        if exclude_patterns and any(fnmatch(rel, p) for p in exclude_patterns):
            continue
        dirs.append(parent)
    return sorted(dirs)


def iter_tf_files(
    root: Path,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> Iterator[Path]:
    for directory in find_tf_directories(root, include_patterns, exclude_patterns):
        yield from sorted(directory.glob("*.tf"))
