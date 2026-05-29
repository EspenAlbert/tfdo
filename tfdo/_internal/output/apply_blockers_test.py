from __future__ import annotations

from pathlib import Path

from tfdo._internal.output.apply_blockers import build_apply_blockers
from tfdo._internal.output.apply_state import ApplyProgressState, ApplyResourceStatus
from tfdo._internal.output.parser import parse_plan_file


def test_create_flat_blockers(create_flat_plan: Path) -> None:
    blockers = build_apply_blockers(create_flat_plan)
    assert blockers["local_file.config"] == frozenset({"random_pet.server", "random_string.suffix"})


def test_create_modules_dns_record(create_modules_plan: Path) -> None:
    blockers = build_apply_blockers(create_modules_plan)
    dns = "module.networking.module.dns.local_file.dns_record"
    assert "module.networking.random_id.vpc_id" in blockers[dns]


def test_active_blockers_filters_in_progress(create_flat_plan: Path) -> None:
    plan = parse_plan_file(create_flat_plan)
    state = ApplyProgressState(plan, build_apply_blockers(create_flat_plan))
    state.resources["random_pet.server"].status = ApplyResourceStatus.IN_PROGRESS
    waiting = state.active_blockers("local_file.config")
    assert waiting == ["random_pet.server"]
