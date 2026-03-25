from pathlib import Path

from tfdo._internal.inspect import hcl_resource_paths as hrp
from tfdo._internal.inspect.hcl_resource_paths import (
    HclParseError,
    HclResourcePathsResult,
    collect_resource_argument_paths,
)


class _ExcWithNonPositiveLineCol(Exception):
    line = 0
    column = 0


_SAMPLE_OK_MAIN = """
resource "aws_s3_bucket" "logs" {
  bucket = "mybucket"
  count  = 1
  tags = {
    Env = "prod"
  }
}

resource "aws_instance" "web" {
  ami           = "ami-123"
  instance_type = "t3.micro"

  advanced_configuration = {
    javascript_enabled = true
  }

  lifecycle {
    ignore_changes = [tags]
  }

  ebs_block_device {
    volume_size = 10
    encryption {
      enabled = true
    }
  }

  ebs_block_device {
    volume_size = 20
    device_name = "/dev/sdf"
  }

  dynamic "ingress" {
    for_each = [1]
    content {
      from_port = 443
    }
  }
}
"""

_SAMPLE_OK_EXTRA = """
resource "aws_s3_bucket" "logs" {
  force_destroy = true
}
"""

_SAMPLE_BAD = """
resource "x" "y" {
"""


def test_collect_regression_ok(file_regression, tmp_path: Path) -> None:
    (tmp_path / "main.tf").write_text(_SAMPLE_OK_MAIN, encoding="utf-8")
    (tmp_path / "extra.tf").write_text(_SAMPLE_OK_EXTRA, encoding="utf-8")
    result = collect_resource_argument_paths(tmp_path)
    file_regression.check(result.to_canonical_json())


def test_collect_regression_parse_error(file_regression, tmp_path: Path) -> None:
    (tmp_path / "broken.tf").write_text(_SAMPLE_BAD, encoding="utf-8")
    result = collect_resource_argument_paths(tmp_path)
    file_regression.check(result.to_canonical_json(error_paths_relative_to=tmp_path))


def test_empty_directory(tmp_path: Path) -> None:
    result = collect_resource_argument_paths(tmp_path)
    assert not result.rows
    assert not result.errors


def test_inline_object_nested_dict_emits_parent_child_only(tmp_path: Path) -> None:
    (tmp_path / "main.tf").write_text(
        'resource "null_resource" "x" {\n  outer = {\n    inner = {\n      leaf = 1\n    }\n  }\n}\n',
        encoding="utf-8",
    )
    result = collect_resource_argument_paths(tmp_path)
    row = next(r for r in result.rows if r.address == "null_resource.x")
    assert set(row.attribute_paths) == {"outer.inner"}


def test_hcl_resource_paths_canonical_json_relativize_falls_back_outside_root(tmp_path: Path) -> None:
    err = HclParseError(path=Path("/nope/out.tf"), message="m")
    text = HclResourcePathsResult(errors=[err]).to_canonical_json(error_paths_relative_to=tmp_path)
    assert "out.tf" in text


def test_to_parse_error_clamps_non_positive_line_column() -> None:
    e = hrp.to_parse_error(Path("a.tf"), _ExcWithNonPositiveLineCol())
    assert e.line is None
    assert e.column is None


def test_merge_skips_non_object_resource_entries() -> None:
    acc: dict[tuple[Path, str], set[str]] = {}
    hrp._merge_parsed_into_file(
        {"resource": [1, {"aws_instance": "bad"}, {"aws_instance": {"lbl": "notdict"}}]}, Path("f.tf"), acc
    )
    assert acc == {}


def test_lifecycle_precondition_dict_body_emits_no_lifecycle_paths() -> None:
    body = {
        "bucket": "b",
        "lifecycle": {
            "precondition": [
                {
                    "condition": "length(local.x) >= 3",
                    "error_message": "too short",
                }
            ],
        },
    }
    paths = hrp._filter_meta_paths(hrp._paths_from_resource_body(body))
    assert "lifecycle" not in paths
    assert not any(p.startswith("lifecycle.") for p in paths)
    assert "bucket" in paths


def test_paths_helpers_cover_dynamic_and_nested_branches() -> None:
    assert hrp._paths_from_dynamic("x") == set()
    assert hrp._paths_from_nested_block("blk", [{"k": [{"nested_arg": 1}]}]) == set()
    assert hrp._paths_from_dynamic_block("d", "nope") == set()
    assert hrp._paths_from_dynamic_block("d", {"content": {}}) == set()
    got = hrp._paths_from_dynamic_block("d", {"content": [[], {"a": {"x": 1}}]})
    assert "d.a.x" in got


def test_hidden_dir_tf_is_scanned_parse_error_recorded(tmp_path: Path) -> None:
    (tmp_path / "ok.tf").write_text('resource "null_resource" "a" { }\n', encoding="utf-8")
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    (hidden / "bad.tf").write_text("not valid hcl {{{\n", encoding="utf-8")
    result = collect_resource_argument_paths(tmp_path)
    assert any(r.address == "null_resource.a" for r in result.rows)
    assert len(result.errors) == 1
    assert result.errors[0].path.name == "bad.tf"
