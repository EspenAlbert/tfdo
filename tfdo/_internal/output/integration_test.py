from __future__ import annotations

import pytest

from tfdo._internal.output.conftest import render_fixture
from tfdo._internal.output.testdata_paths import TESTDATA_DIR

FIXTURE_NAMES = (
    "01_create_flat",
    "02_create_modules",
    "03_update",
    "04_replace",
    "05_destroy",
    "06_outputs_only",
    "07_drift",
)


@pytest.mark.parametrize("basename", FIXTURE_NAMES)
def test_render_fixture(basename: str, capture_console, file_regression) -> None:
    rendered = render_fixture(TESTDATA_DIR / f"{basename}.json", capture_console)
    file_regression.check(rendered, basename=basename, extension=".txt")


def test_render_empty(empty_plan, capture_console, file_regression) -> None:
    rendered = render_fixture(None, capture_console, plan=empty_plan)
    file_regression.check(rendered, basename="empty", extension=".txt")
