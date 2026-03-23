from pathlib import Path

from tfdo._internal.inspect.hcl_resource_paths import collect_resource_argument_paths

_SAMPLE_OK_MAIN = """
resource "aws_s3_bucket" "logs" {
  bucket = "mybucket"
  tags = {
    Env = "prod"
  }
}

resource "aws_instance" "web" {
  ami           = "ami-123"
  instance_type = "t3.micro"

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
    assert not result.resources
    assert not result.errors


def test_skips_dot_path_segments(tmp_path: Path) -> None:
    (tmp_path / "ok.tf").write_text('resource "null_resource" "a" { }\n', encoding="utf-8")
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    (hidden / "bad.tf").write_text("not valid hcl {{{\n", encoding="utf-8")
    result = collect_resource_argument_paths(tmp_path)
    assert "null_resource.a" in result.resources
    assert not result.errors
