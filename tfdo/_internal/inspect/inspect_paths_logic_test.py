from pathlib import Path

from tfdo._internal.inspect.inspect_paths_logic import InspectHclPathsInput, inspect_hcl_paths


def test_inspect_hcl_paths_delegates(tmp_path: Path) -> None:
    (tmp_path / "a.tf").write_text('resource "null_resource" "x" { }\n', encoding="utf-8")
    result = inspect_hcl_paths(InspectHclPathsInput(root=tmp_path))
    assert any(r.address == "null_resource.x" for r in result.rows)
