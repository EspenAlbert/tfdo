# path-sync copy -n python-template
"""Replace relative source links with GitHub URLs in docs."""

import re
import sys
from pathlib import Path

if len(sys.argv) < 2:
    raise SystemExit("Usage: fix_source_links.py <REPO_URL>")

REPO_URL = sys.argv[1]
BRANCH = "main"
DOCS_DIR = Path(__file__).parent.parent / "docs"

# Pattern: [source](../../pkg_name/_internal/module.py#L81)
RELATIVE_SOURCE_PATTERN = re.compile(r"\[source\]\((?P<rel_path>\.\./[^)]+)\)")


def to_github_url(rel_path: str, doc_file: Path) -> str:
    """Convert relative path to absolute GitHub URL."""
    resolved = (doc_file.parent / rel_path).resolve()
    repo_root = DOCS_DIR.parent
    try:
        repo_relative = resolved.relative_to(repo_root)
    except ValueError:
        return rel_path
    return f"{REPO_URL}/blob/{BRANCH}/{repo_relative}"


def fix_links_in_file(file_path: Path) -> bool:
    """Fix source links in a single file. Returns True if modified."""
    content = file_path.read_text()

    def replace_source_link(match: re.Match[str]) -> str:
        rel_path = match.group("rel_path")
        github_url = to_github_url(rel_path, file_path)
        return f"[source]({github_url})"

    new_content = RELATIVE_SOURCE_PATTERN.sub(replace_source_link, content)
    if new_content != content:
        file_path.write_text(new_content)
        return True
    return False


def main() -> None:
    modified_count = 0
    for md_file in DOCS_DIR.rglob("*.md"):
        if fix_links_in_file(md_file):
            print(f"Fixed: {md_file.relative_to(DOCS_DIR)}")  # noqa: T201
            modified_count += 1
    print(f"Modified {modified_count} file(s)")  # noqa: T201


if __name__ == "__main__":
    main()
