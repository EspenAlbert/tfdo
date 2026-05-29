from __future__ import annotations

from pathlib import Path

from tfdo._internal.output.apply_blockers import ExpressionValue, build_apply_blockers, collect_references
from tfdo._internal.output.apply_state import ApplyPhase, ApplyProgressState, ApplyResourceStatus
from tfdo._internal.output.parser import parse_plan_file

CPA_AUTH = "module.gcp.module.cloud_provider_access[0].mongodbatlas_cloud_provider_access_authorization.this"
CPA_SETUP = "module.gcp.module.cloud_provider_access[0].mongodbatlas_cloud_provider_access_setup.this"
LOG_BUCKET = "module.gcp.module.log_integration[0].google_storage_bucket.atlas[0]"
LOG_IAM = 'module.gcp.module.log_integration[0].google_storage_bucket_iam_member.atlas["default"]'
LOG_INTEGRATION = "module.gcp.module.log_integration[0].mongodbatlas_log_integration.this[0]"
LOG_SLEEP = "module.gcp.module.log_integration[0].time_sleep.iam_propagation[0]"


def test_create_flat_blockers(create_flat_plan: Path) -> None:
    blockers = build_apply_blockers(create_flat_plan)
    assert blockers["local_file.config"] == frozenset({"random_pet.server", "random_string.suffix"})


def test_create_modules_dns_record(create_modules_plan: Path) -> None:
    blockers = build_apply_blockers(create_modules_plan)
    dns = "module.networking.module.dns.local_file.dns_record"
    assert "module.networking.random_id.vpc_id" in blockers[dns]


def test_count_module_blockers(apply_blockers_count_plan: Path) -> None:
    blockers = build_apply_blockers(apply_blockers_count_plan)
    assert blockers[CPA_AUTH] == frozenset({CPA_SETUP})
    assert LOG_BUCKET in blockers[LOG_IAM]
    assert LOG_SLEEP in blockers[LOG_INTEGRATION]
    assert LOG_BUCKET in blockers[LOG_SLEEP]
    assert LOG_IAM in blockers[LOG_SLEEP]


def test_active_blockers_includes_pending_and_in_progress(create_flat_plan: Path) -> None:
    plan = parse_plan_file(create_flat_plan)
    state = ApplyProgressState(plan, build_apply_blockers(create_flat_plan))
    state.resources["random_pet.server"].status = ApplyResourceStatus.IN_PROGRESS
    assert state.active_blockers("local_file.config") == ["random_pet.server", "random_string.suffix"]

    state.resources["random_pet.server"].status = ApplyResourceStatus.COMPLETED
    assert state.active_blockers("local_file.config") == ["random_string.suffix"]


def test_pending_resources_sorted(apply_blockers_count_plan: Path) -> None:
    plan = parse_plan_file(apply_blockers_count_plan)
    blockers = build_apply_blockers(apply_blockers_count_plan)
    state = ApplyProgressState(plan, blockers)
    state.phase = ApplyPhase.APPLYING
    state.resources[CPA_SETUP].status = ApplyResourceStatus.IN_PROGRESS
    ordered = [resource.addr for resource in state.pending_resources_sorted()]
    assert ordered == [LOG_BUCKET, LOG_IAM, LOG_INTEGRATION, CPA_AUTH, LOG_SLEEP]


def test_collect_references_nested_block() -> None:
    expression: ExpressionValue = [
        {"enabled": {"references": ["var.create_gcs_bucket", "google_storage_bucket.atlas"]}},
    ]
    assert collect_references(expression) == {"var.create_gcs_bucket", "google_storage_bucket.atlas"}
