from collections.abc import Iterator
from fnmatch import fnmatch
from pathlib import Path

TERRAFORM_DIR = ".terraform"


def _is_hidden_path(root: Path, path: Path) -> bool:
    return any(part.startswith(".") for part in path.relative_to(root).parts)


def find_tf_directories(
    root: Path,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    *,
    include_hidden: bool = False,
) -> list[Path]:
    dirs: list[Path] = []
    for path in root.rglob("*.tf"):
        if not include_hidden and _is_hidden_path(root, path):
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
    *,
    include_hidden: bool = False,
) -> Iterator[Path]:
    for directory in find_tf_directories(root, include_patterns, exclude_patterns, include_hidden=include_hidden):
        yield from sorted(directory.glob("*.tf"))
