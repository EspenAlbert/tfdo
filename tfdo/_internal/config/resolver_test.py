from __future__ import annotations

from pathlib import Path

import pytest

from tfdo._internal.config.env_var_loader import ENV_VARS_DIRS_KEY
from tfdo._internal.config.resolver import resolve_run_dir
from tfdo._internal.settings import TfDoSettings


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


@pytest.fixture()
def fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "fixture"
    _write(root / "tfdo.yaml", "providers:\n  - name: mongodbatlas\n    constraint: '~> 2.0'\n")
    _write(
        root / "provider_hints.yaml",
        "mongodbatlas:\n  source: mongodb/mongodbatlas\n  auth_bundles:\n    - name: api_keys\n      secrets: [MONGODB_ATLAS_CLIENT_ID, MONGODB_ATLAS_CLIENT_SECRET]\n  auth_variables:\n    - env: MONGODB_ATLAS_ORG_ID\n      tf_var: org_id\n",
    )
    _write(root / "envs" / "dev" / "tfdo.yaml", "")
    return root


@pytest.fixture()
def settings(tmp_path: Path) -> TfDoSettings:
    return TfDoSettings.for_testing(tmp_path)


def test_negative_case_empty_run_dir(fixture_root: Path, settings: TfDoSettings, tmp_path: Path) -> None:
    """No module calls + no run-dir tfdo.yaml → empty required_providers despite root declaring mongodbatlas."""
    empty_dir = fixture_root / "envs" / "dev" / "empty"
    empty_dir.mkdir(parents=True, exist_ok=True)

    result = resolve_run_dir(
        fixture_root,
        "dev",
        "envs/dev/empty",
        settings=settings,
        os_env={ENV_VARS_DIRS_KEY: "nonexistent", "TFDO_ENV_VARS_LOAD": "skip"},
    )

    assert result.required_providers == []
    assert result.resolved_modules == []


def test_force_inject_from_run_dir_tfdo_yaml(fixture_root: Path, settings: TfDoSettings, tmp_path: Path) -> None:
    """Run-dir tfdo.yaml with providers:[{name: random}] → injects random with constraint=None."""
    forced_dir = fixture_root / "envs" / "dev" / "forced"
    _write(forced_dir / "tfdo.yaml", "providers:\n  - name: random\n")

    result = resolve_run_dir(
        fixture_root,
        "dev",
        "envs/dev/forced",
        settings=settings,
        os_env={ENV_VARS_DIRS_KEY: "nonexistent", "TFDO_ENV_VARS_LOAD": "skip"},
    )

    assert len(result.required_providers) == 1
    rp = result.required_providers[0]
    assert rp.name == "random"
    assert rp.constraint is None
    assert rp.source == "hashicorp/random"
    assert rp.is_declared_in_tfdo_yaml
    assert not rp.has_hints_entry
    assert rp.is_force_injected


def test_classification_flags(fixture_root: Path, settings: TfDoSettings) -> None:
    """Provider declared in both HCL and tfdo.yaml hierarchy gets correct flags."""
    run_dir = fixture_root / "envs" / "dev" / "classified"
    _write(
        run_dir / "versions.tf",
        'terraform {\n  required_providers {\n    mongodbatlas = {\n      source  = "mongodb/mongodbatlas"\n      version = "~> 2.0"\n    }\n  }\n}\n',
    )

    result = resolve_run_dir(
        fixture_root,
        "dev",
        "envs/dev/classified",
        settings=settings,
        os_env={ENV_VARS_DIRS_KEY: "nonexistent", "TFDO_ENV_VARS_LOAD": "skip"},
    )

    assert len(result.required_providers) == 1
    rp = result.required_providers[0]
    assert rp.name == "mongodbatlas"
    assert rp.is_declared_in_hcl
    assert rp.is_declared_in_tfdo_yaml
    assert rp.has_hints_entry
    assert not rp.is_force_injected
    assert rp.source == "mongodb/mongodbatlas"
    assert rp.constraint == "~> 2.0"


def test_env_override_constraint(fixture_root: Path, settings: TfDoSettings) -> None:
    """Prod env override tightens the mongodbatlas constraint."""
    _write(
        fixture_root / "envs" / "prod" / "tfdo.yaml",
        "providers:\n  - name: mongodbatlas\n    constraint: '~> 2.10'\n",
    )
    run_dir = fixture_root / "envs" / "prod" / "overridden"
    _write(
        run_dir / "versions.tf",
        "terraform {\n  required_providers {\n    mongodbatlas = {}\n  }\n}\n",
    )

    result = resolve_run_dir(
        fixture_root,
        "prod",
        "envs/prod/overridden",
        settings=settings,
        os_env={ENV_VARS_DIRS_KEY: "nonexistent", "TFDO_ENV_VARS_LOAD": "skip"},
    )

    rp = next(p for p in result.required_providers if p.name == "mongodbatlas")
    assert rp.constraint == "~> 2.10"
