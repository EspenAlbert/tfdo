from __future__ import annotations

from tfdo._internal.inspect.name_normalize import build_name_mapping, normalize_api_path


def test_normalize_api_path() -> None:
    assert normalize_api_path("connectionStrings.awsPrivateLink.*") == "connection_strings.aws_private_link"
    assert normalize_api_path("replicationSpecs[].regionConfigs[].electableSpecs.instanceSize") == (
        "replication_specs.region_configs.electable_specs.instance_size"
    )
    assert normalize_api_path("replicationSpecs[]") == "replication_specs"
    assert normalize_api_path("simple") == "simple"


def test_build_name_mapping_exact_and_prefix() -> None:
    api_paths = {"clusterType", "tags[].key", "tags[].value", "biConnector.enabled"}
    tf_paths = {"cluster_type", "tags", "bi_connector_config.enabled"}
    mapping = build_name_mapping(api_paths, tf_paths, overrides={"bi_connector": "bi_connector_config"})
    assert "clusterType" in mapping.matched
    assert mapping.matched["clusterType"] == "cluster_type"
    assert "tags" in mapping.prefix_matched
    assert not mapping.api_only
    assert not mapping.tf_only


def test_build_name_mapping_fuzzy() -> None:
    api_paths = {"diskSizeGb"}
    tf_paths = {"disk_size_gb"}
    mapping = build_name_mapping(api_paths, tf_paths)
    assert "diskSizeGb" in mapping.matched or "diskSizeGb" in mapping.fuzzy_matched
