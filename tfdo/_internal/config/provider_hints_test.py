from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tfdo._internal.config.provider_hints import (
    AuthBundle,
    ModuleHint,
    ProviderHints,
    UnknownInheritsFromError,
    UnknownProviderError,
    VariableMapping,
    get_provider_hints,
    load_provider_hints,
)

_ATLAS_HINTS = ProviderHints(
    auth_bundles=[AuthBundle(name="api_keys", secrets=["ATLAS_CLIENT_ID", "ATLAS_CLIENT_SECRET"])],
    auth_variables=[VariableMapping(env="ATLAS_ORG_ID", tf_var="org_id")],
)

_AWS_HINTS = ProviderHints(
    auth_bundles=[
        AuthBundle(name="access_keys", secrets=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]),
        AuthBundle(name="sso", variables=["AWS_PROFILE"]),
        AuthBundle(name="assume_role", inherits_from="access_keys", secrets=["AWS_ROLE_ARN"]),
    ]
)


def test_bundle_satisfied_when_all_secrets_present():
    bundle = AuthBundle(name="api_keys", secrets=["A", "B"])
    assert bundle.is_satisfied({"A": "1", "B": "2"})


def test_bundle_not_satisfied_when_secret_missing():
    bundle = AuthBundle(name="api_keys", secrets=["A", "B"])
    assert not bundle.is_satisfied({"A": "1"})


def test_bundle_satisfied_with_variables():
    bundle = AuthBundle(name="sso", variables=["AWS_PROFILE"])
    assert bundle.is_satisfied({"AWS_PROFILE": "dev"})


def test_bundle_inherits_from_merges_parent_secrets():
    by_name = {b.name: b for b in _AWS_HINTS.auth_bundles}
    assume_role = by_name["assume_role"]
    reqs = assume_role.effective_requirements(by_name)
    assert set(reqs.secrets) == {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_ROLE_ARN"}


def test_bundle_inherits_from_is_satisfied_requires_parent_and_own():
    by_name = {b.name: b for b in _AWS_HINTS.auth_bundles}
    assume_role = by_name["assume_role"]
    full_env = {"AWS_ACCESS_KEY_ID": "x", "AWS_SECRET_ACCESS_KEY": "y", "AWS_ROLE_ARN": "z"}
    partial_env = {"AWS_ACCESS_KEY_ID": "x", "AWS_SECRET_ACCESS_KEY": "y"}
    assert assume_role.is_satisfied(full_env, by_name)
    assert not assume_role.is_satisfied(partial_env, by_name)


def test_satisfied_bundles_returns_only_matching():
    env = {"AWS_PROFILE": "dev"}
    result = _AWS_HINTS.satisfied_bundles(env)
    assert [b.name for b in result] == ["sso"]


def test_satisfied_bundles_multiple_satisfied():
    env = {"AWS_ACCESS_KEY_ID": "x", "AWS_SECRET_ACCESS_KEY": "y", "AWS_PROFILE": "dev"}
    result = _AWS_HINTS.satisfied_bundles(env)
    assert {b.name for b in result} == {"access_keys", "sso"}


def test_satisfied_bundles_empty_when_none_match():
    assert _ATLAS_HINTS.satisfied_bundles({}) == []


def test_load_provider_hints_from_yaml(tmp_path: Path):
    data = {
        "mongodbatlas": {
            "auth_bundles": [{"name": "api_keys", "secrets": ["ATLAS_ID", "ATLAS_SECRET"]}],
            "auth_variables": [{"env": "ATLAS_ORG_ID", "tf_var": "org_id"}],
            "modules": [{"source": "terraform-mongodbatlas-modules/cluster", "alias": "cluster"}],
        },
        "aws": {
            "auth_bundles": [
                {"name": "access_keys", "secrets": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]},
                {"name": "sso", "variables": ["AWS_PROFILE"]},
                {"name": "assume_role", "inherits_from": "access_keys", "secrets": ["AWS_ROLE_ARN"]},
            ]
        },
    }
    hints_file = tmp_path / "provider_hints.yaml"
    hints_file.write_text(yaml.dump(data))

    registry = load_provider_hints(hints_file)

    atlas = registry["mongodbatlas"]
    assert atlas.auth_bundles[0].name == "api_keys"
    assert atlas.auth_variables[0].tf_var == "org_id"
    assert atlas.modules[0].alias == "cluster"

    aws = registry["aws"]
    assert len(aws.auth_bundles) == 3
    assert aws.auth_bundles[2].inherits_from == "access_keys"


def test_load_provider_hints_raises_on_bad_inherits_from(tmp_path: Path):
    data = {
        "aws": {
            "auth_bundles": [
                {"name": "assume_role", "inherits_from": "nonexistent", "secrets": ["AWS_ROLE_ARN"]},
            ]
        }
    }
    hints_file = tmp_path / "provider_hints.yaml"
    hints_file.write_text(yaml.dump(data))

    with pytest.raises(UnknownInheritsFromError, match="nonexistent"):
        load_provider_hints(hints_file)


def test_get_provider_hints_raises_on_missing_provider():
    registry = {"mongodbatlas": _ATLAS_HINTS}
    with pytest.raises(UnknownProviderError, match="aws"):
        get_provider_hints(registry, "aws")


def test_closest_bundle_returns_bundle_with_fewest_missing():
    env = {"ATLAS_CLIENT_ID": "x"}
    result = _ATLAS_HINTS.closest_bundle(env)
    assert result is not None
    bundle, missing = result
    assert bundle.name == "api_keys"
    assert missing == ["ATLAS_CLIENT_SECRET"]


def test_closest_bundle_multi_bundle_picks_least_missing():
    env = {"AWS_ACCESS_KEY_ID": "x", "AWS_SECRET_ACCESS_KEY": "y"}
    result = _AWS_HINTS.closest_bundle(env)
    assert result is not None
    bundle, missing = result
    assert bundle.name == "access_keys"
    assert missing == []


def test_closest_bundle_returns_none_when_no_bundles():
    hints = ProviderHints()
    assert hints.closest_bundle({}) is None


def test_provider_hints_modules_field():
    hints = ProviderHints(
        modules=[
            ModuleHint(source="terraform-mongodbatlas-modules/cluster", alias="cluster"),
            ModuleHint(source="terraform-mongodbatlas-modules/project", alias="project"),
        ]
    )
    assert hints.modules[0].alias == "cluster"
    assert hints.modules[1].source == "terraform-mongodbatlas-modules/project"
