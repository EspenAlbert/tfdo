from pathlib import Path

TERRAFORM_DIR = ".terraform"


def find_tf_directories(root: Path) -> list[Path]:
    """Walk root, return sorted directories containing .tf files, excluding .terraform/ subtrees."""
    dirs: list[Path] = []
    for path in root.rglob("*.tf"):
        if TERRAFORM_DIR in path.parts:
            continue
        if path.parent not in dirs:
            dirs.append(path.parent)
    return sorted(dirs)
