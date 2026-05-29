from __future__ import annotations

from pathlib import Path

TESTDATA_DIR = Path(__file__).parent / "testdata"
APPLY_PROGRESS_DIR = TESTDATA_DIR / "apply_progress"


def apply_progress_fixture(name: str) -> Path:
    return APPLY_PROGRESS_DIR / name


def load_apply_progress_lines(name: str) -> list[str]:
    return [line for line in apply_progress_fixture(name).read_text().splitlines() if line.strip()]
