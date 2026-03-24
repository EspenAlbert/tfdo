from __future__ import annotations

from pathlib import Path

import pytest
from zero_3rdparty.file_utils import ensure_parents_write_text

from tfdo._internal.schema import terraform_cli_config as tf_cli

_OBJECT_DEV_OVERRIDES = """provider_installation {
  dev_overrides = {
    "mongodb/mongodbatlas" = "/opt/plugins"
  }
  direct {}
}
"""


def test_normalize_registry_source_key_strips_host() -> None:
    assert tf_cli.normalize_registry_source_key("registry.terraform.io/hashicorp/aws") == "hashicorp/aws"
    assert tf_cli.normalize_registry_source_key("hashicorp/aws") == "hashicorp/aws"


def test_parse_dev_overrides_block_form_quoted_keys(tmp_path: Path) -> None:
    p = tmp_path / "cli.tfrc"
    ensure_parents_write_text(
        p,
        """provider_installation {
  dev_overrides {
    "mongodb/mongodbatlas" = "/Users/example/code/provider/bin"
  }
  direct {}
}
""",
    )
    m = tf_cli.parse_dev_overrides(p)
    assert m["mongodb/mongodbatlas"] == "/Users/example/code/provider/bin"


def test_parse_dev_overrides_object_form(tmp_path: Path) -> None:
    p = tmp_path / "cli.tfrc"
    ensure_parents_write_text(p, _OBJECT_DEV_OVERRIDES)
    m = tf_cli.parse_dev_overrides(p)
    assert m["mongodb/mongodbatlas"] == "/opt/plugins"
    assert tf_cli.lookup_plugin_dir(m, registry_source="mongodb/mongodbatlas") == "/opt/plugins"


def test_parse_dev_overrides_second_block_wins_same_normalized_source(tmp_path: Path) -> None:
    p = tmp_path / "cli.tfrc"
    ensure_parents_write_text(
        p,
        """provider_installation {
  dev_overrides = {
    "hashicorp/aws" = "/first"
  }
}
provider_installation {
  dev_overrides = {
    "registry.terraform.io/hashicorp/aws" = "/second"
  }
}
""",
    )
    m = tf_cli.parse_dev_overrides(p)
    assert m["hashicorp/aws"] == "/second"


def test_parse_dev_overrides_invalid_hcl_without_dev_block_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.tfrc"
    ensure_parents_write_text(p, "{{{ not valid hcl")
    with pytest.raises(ValueError, match="not valid HCL2"):
        tf_cli.parse_dev_overrides(p)


def test_parse_dev_overrides_unclosed_dev_block_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.tfrc"
    ensure_parents_write_text(
        p,
        """provider_installation {
  dev_overrides {
    "a/b" = "/x"
""",
    )
    with pytest.raises(ValueError, match="unclosed or malformed"):
        tf_cli.parse_dev_overrides(p)


def test_subprocess_env_for_schema_temp_dir_ephemeral(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = tmp_path / "user.tfrc"
    ensure_parents_write_text(
        cfg,
        """provider_installation {
  dev_overrides = {
    "acme/widget" = "/plugins"
  }
  direct {}
}
""",
    )
    monkeypatch.setenv(tf_cli.TF_CLI_CONFIG_FILE_ENV, str(cfg))
    ws = tmp_path / "ws"
    ws.mkdir()
    env = tf_cli.subprocess_env_for_schema_temp_dir(workspace_root=ws, registry_source="acme/widget")
    assert env is not None
    assert env[tf_cli.TF_CLI_CONFIG_FILE_ENV].endswith("tfdo.dev.tfrc")
    assert (ws / "tfdo.dev.tfrc").is_file()
