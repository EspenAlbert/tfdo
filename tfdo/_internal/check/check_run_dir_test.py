from __future__ import annotations

from pathlib import Path

from tfdo._internal.check.check_run_dir import check_resolved, check_run_dir
from tfdo._internal.check.models import DeclarationCase
from tfdo._internal.config.env_var_loader import ENV_VARS_DIRS_KEY, LoadResult
from tfdo._internal.config.provider_hints import AuthBundle, ProviderHints
from tfdo._internal.config.resolver import ResolvedProvider, ResolvedRunDirConfig
from tfdo._internal.settings import TfDoSettings

_SKIP_ENV = {ENV_VARS_DIRS_KEY: "nonexistent", "TFDO_ENV_VARS_LOAD": "skip"}

_ATLAS_HINTS = ProviderHints(
    auth_bundles=[AuthBundle(name="api_keys", secrets=["MONGODB_ATLAS_CLIENT_ID", "MONGODB_ATLAS_CLIENT_SECRET"])]
)
_AWS_HINTS = ProviderHints(
    auth_bundles=[
        AuthBundle(name="access_keys", secrets=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]),
        AuthBundle(name="sso", variables=["AWS_PROFILE"]),
        AuthBundle(name="assume_role", inherits_from="access_keys", secrets=["AWS_ROLE_ARN"]),
    ]
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _base_fixture(root: Path, hints_yaml: str = "") -> None:
    _write(root / "provider_hints.yaml", hints_yaml or "{}\n")
    _write(root / "envs" / "dev" / "tfdo.yaml", "")


def _settings(tmp_path: Path) -> TfDoSettings:
    return TfDoSettings.for_testing(tmp_path)


def _resolved_provider(name: str = "mongodbatlas", **kwargs) -> ResolvedProvider:
    return ResolvedProvider(name=name, **kwargs)


def _make_resolved(provider: ResolvedProvider, hints: ProviderHints | None = None) -> ResolvedRunDirConfig:
    return ResolvedRunDirConfig(
        required_providers=[provider],
        resolved_modules=[],
        provider_hints={"mongodbatlas": hints} if hints else {},
        auth_variables=[],
        loaded_env_vars=LoadResult(merged={}, loaded_paths=[], reason="skip"),
    )


# --- declaration cases ---


def test_declaration_case_a_unknown_provider(tmp_path: Path) -> None:
    """Provider from HCL only, no hints, no tfdo.yaml declaration → Case A error."""
    root = tmp_path / "fixture"
    _base_fixture(root)
    _write(
        root / "envs" / "dev" / "run" / "versions.tf",
        "terraform {\n  required_providers {\n    random = {}\n  }\n}\n",
    )
    result = check_run_dir(root, "envs/dev/run", {**_SKIP_ENV}, _settings(tmp_path))
    assert not result.is_ok
    p = result.providers[0]
    assert p.declaration.case == DeclarationCase.no_hints_no_declaration
    assert not p.declaration.ok


def test_declaration_case_b_force_injected_no_hints(tmp_path: Path) -> None:
    """Run-dir own tfdo.yaml declares random, no hints → Case B ok (hashicorp fallback)."""
    root = tmp_path / "fixture"
    _base_fixture(root)
    _write(root / "envs" / "dev" / "forced" / "tfdo.yaml", "providers:\n  - name: random\n")
    result = check_run_dir(root, "envs/dev/forced", {**_SKIP_ENV}, _settings(tmp_path))
    assert result.is_ok
    p = result.providers[0]
    assert p.declaration.case == DeclarationCase.force_injected_no_hints
    assert p.declaration.ok


def test_declaration_case_c_parent_declaration_no_hints(tmp_path: Path) -> None:
    """Root tfdo.yaml declares acme-cloud; run-dir HCL uses it; no hints → Case C error."""
    root = tmp_path / "fixture"
    _base_fixture(root, hints_yaml="{}\n")
    _write(root / "tfdo.yaml", "providers:\n  - name: acme-cloud\n    constraint: '~> 1.0'\n")
    _write(
        root / "envs" / "dev" / "run" / "versions.tf",
        "terraform {\n  required_providers {\n    acme-cloud = {}\n  }\n}\n",
    )
    result = check_run_dir(root, "envs/dev/run", {**_SKIP_ENV}, _settings(tmp_path))
    assert not result.is_ok
    p = result.providers[0]
    assert p.declaration.case == DeclarationCase.parent_constraint_no_hints
    assert not p.declaration.ok


def test_declaration_case_d_hints_exist_not_declared(tmp_path: Path) -> None:
    """Provider discovered via local module OUTSIDE run-dir; hints exist; not declared → Case D error.

    The module must live outside the run-dir so parse_dir_entities(run_dir) does not pick it
    up via **/*.tf - otherwise the provider would appear in hcl_names and Case D wouldn't fire.
    """
    root = tmp_path / "fixture"
    _base_fixture(
        root,
        hints_yaml="mongodbatlas:\n  source: mongodb/mongodbatlas\n  auth_bundles:\n    - name: api_keys\n      secrets: [MONGODB_ATLAS_CLIENT_ID, MONGODB_ATLAS_CLIENT_SECRET]\n",
    )
    # Shared module lives at the fixture root, outside any run-dir.
    _write(
        root / "shared_modules" / "atlas" / "versions.tf",
        'terraform {\n  required_providers {\n    mongodbatlas = { source = "mongodb/mongodbatlas" }\n  }\n}\n',
    )
    _write(
        root / "envs" / "dev" / "run" / "main.tf",
        'module "atlas" {\n  source = "../../../shared_modules/atlas"\n}\n',
    )
    result = check_run_dir(root, "envs/dev/run", {**_SKIP_ENV}, _settings(tmp_path))
    assert not result.is_ok
    p = result.providers[0]
    assert p.declaration.case == DeclarationCase.undeclared_with_hints
    assert not p.declaration.ok


# --- credential cases (use check_resolved to avoid filesystem setup) ---


def test_credentials_satisfied() -> None:
    rp = _resolved_provider(has_hints_entry=True, is_declared_in_tfdo_yaml=True)
    resolved = _make_resolved(rp, _ATLAS_HINTS)
    env = {"MONGODB_ATLAS_CLIENT_ID": "id", "MONGODB_ATLAS_CLIENT_SECRET": "secret"}
    result = check_resolved(resolved, env)
    assert result.is_ok
    assert result.providers[0].credentials.satisfied_bundle == "api_keys"


def test_credentials_missing_one() -> None:
    rp = _resolved_provider(has_hints_entry=True, is_declared_in_tfdo_yaml=True)
    resolved = _make_resolved(rp, _ATLAS_HINTS)
    env = {"MONGODB_ATLAS_CLIENT_ID": "id"}
    result = check_resolved(resolved, env)
    assert not result.is_ok
    creds = result.providers[0].credentials
    assert not creds.satisfied
    assert creds.closest_bundle == "api_keys"
    assert creds.missing_keys == ["MONGODB_ATLAS_CLIENT_SECRET"]


def _aws_resolved() -> ResolvedRunDirConfig:
    rp = _resolved_provider("aws", has_hints_entry=True, is_declared_in_tfdo_yaml=True)
    return ResolvedRunDirConfig(
        required_providers=[rp],
        resolved_modules=[],
        provider_hints={"aws": _AWS_HINTS},
        auth_variables=[],
        loaded_env_vars=LoadResult(merged={}, loaded_paths=[], reason="skip"),
    )


def test_credentials_multi_bundle_sso_satisfied() -> None:
    resolved = _aws_resolved()
    env = {"AWS_PROFILE": "dev"}
    result = check_resolved(resolved, env)
    assert result.is_ok
    assert result.providers[0].credentials.satisfied_bundle == "sso"


def test_credentials_closest_to_satisfied_access_keys() -> None:
    resolved = _aws_resolved()
    env = {"AWS_ACCESS_KEY_ID": "x", "AWS_SECRET_ACCESS_KEY": "y"}
    result = check_resolved(resolved, env)
    assert result.is_ok
    assert result.providers[0].credentials.satisfied_bundle == "access_keys"
