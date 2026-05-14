from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import NamedTuple

from ask_shell.shell import ShellError, run_and_wait

logger = logging.getLogger(__name__)

_GIT_REMOTE_RE = re.compile(r"(?:https?://[^/]+/|git@[^:]+:)(?P<org>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$")


class GitRemote(NamedTuple):
    org: str
    repo: str


def parse_git_remote_url(url: str) -> GitRemote | None:
    if m := _GIT_REMOTE_RE.match(url.strip()):
        return GitRemote(org=m.group("org"), repo=m.group("repo"))
    return None


def parse_git_remote(work_dir: Path) -> GitRemote | None:
    try:
        run = run_and_wait("git remote get-url origin", cwd=work_dir)
    except ShellError:
        return None
    return parse_git_remote_url(run.stdout_one_line)
