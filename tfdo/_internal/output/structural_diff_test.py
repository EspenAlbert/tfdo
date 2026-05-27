from __future__ import annotations

import json

from tfdo._internal.output.models import Change
from tfdo._internal.output.structural_diff import compute_structural_diff
from tfdo._internal.output.testdata_paths import TESTDATA_DIR


def _cluster_create_change() -> Change:
    payload = json.loads((TESTDATA_DIR / "09_create_atlas_compact.json").read_text())
    for rc in payload["resource_changes"]:
        if rc["type"] == "mongodbatlas_advanced_cluster":
            return Change.model_validate(rc["change"])
    raise ValueError("cluster create change not found")


def test_create_prunes_empty_and_unknown_leaves() -> None:
    change = _cluster_create_change()
    after = change.after or {}
    specs = after["replication_specs"]
    diff = compute_structural_diff(
        None,
        specs,
        show_create_defaults=False,
        after_unknown=change.after_unknown,
    )
    paths = {tuple(line.path) for line in diff}
    assert ("auto_scaling", "compute_enabled") in {(p[-2], p[-1]) for p in paths if len(p) >= 2}
    assert not any(p[-1] == "compute_max_instance_size" for p in paths)
