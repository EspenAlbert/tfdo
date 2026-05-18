from __future__ import annotations

from pathlib import Path

from tfdo._internal.output import plan_artifacts


def test_atomic_write_text(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "plan.json"
    plan_artifacts.atomic_write_text(target, '{"ok": true}')
    assert target.read_text() == '{"ok": true}'
    assert not target.with_suffix(".json.tmp").exists()


def test_export_plan_bin(tmp_path: Path) -> None:
    canonical = tmp_path / "plan.bin"
    canonical.write_bytes(b"tfplan")
    user_out = tmp_path / "out" / "staging.tfplan"
    plan_artifacts.export_plan_bin(canonical, user_out)
    assert user_out.read_bytes() == b"tfplan"
