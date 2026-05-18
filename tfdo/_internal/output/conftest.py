from __future__ import annotations

from pathlib import Path

import pytest

from tfdo._internal.output.testdata_paths import TESTDATA_DIR


@pytest.fixture
def testdata_dir() -> Path:
    return TESTDATA_DIR


@pytest.fixture
def create_flat_plan() -> Path:
    return TESTDATA_DIR / "01_create_flat.json"


@pytest.fixture
def create_modules_plan() -> Path:
    return TESTDATA_DIR / "02_create_modules.json"


@pytest.fixture
def update_plan() -> Path:
    return TESTDATA_DIR / "03_update.json"


@pytest.fixture
def destroy_plan() -> Path:
    return TESTDATA_DIR / "05_destroy.json"


@pytest.fixture
def outputs_only_plan() -> Path:
    return TESTDATA_DIR / "06_outputs_only.json"


@pytest.fixture
def drift_plan() -> Path:
    return TESTDATA_DIR / "07_drift.json"
