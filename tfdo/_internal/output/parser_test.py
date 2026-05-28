from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tfdo._internal.output.models import OutputChange, PlanOutput, ResourceAction
from tfdo._internal.output.parser import PLAN_PARSE_FAILURE_FILENAME, parse_plan_file
from tfdo._internal.settings import TfDoSettings


def test_parse_create_flat(create_flat_plan: Path) -> None:
    plan = parse_plan_file(create_flat_plan)
    assert not plan.errored
    assert plan.applyable is True
    assert plan.complete is True
    assert len(plan.resource_changes) == 3
    for rc in plan.resource_changes:
        assert rc.change.action() == ResourceAction.CREATE
    config = next(rc for rc in plan.resource_changes if rc.address == "local_file.config")
    assert isinstance(config.change.after_unknown, dict)
    assert config.change.after_unknown.get("content") is True


def test_parse_destroy(destroy_plan: Path) -> None:
    plan = parse_plan_file(destroy_plan)
    assert len(plan.resource_changes) == 4
    assert all(rc.change.action() == ResourceAction.DELETE for rc in plan.resource_changes)
    assert any(rc.action_reason for rc in plan.resource_changes)


def test_parse_output_change_structured_after_unknown() -> None:
    plan = PlanOutput.model_validate(
        {
            "format_version": "1.2",
            "errored": False,
            "output_changes": {
                "subnet_ids": {
                    "actions": ["create"],
                    "after_unknown": [True],
                    "before_sensitive": False,
                    "after_sensitive": False,
                }
            },
        }
    )
    assert isinstance(plan.output_changes["subnet_ids"], OutputChange)
    assert plan.output_changes["subnet_ids"].after_unknown == [True]


def test_parse_output_changes(outputs_only_plan: Path) -> None:
    plan = parse_plan_file(outputs_only_plan)
    assert plan.output_changes["deployed_at"].actions == ["create"]
    assert plan.output_changes["deployed_at"].before is None
    assert plan.output_changes["deployed_at"].after == "2026-05-18T19:00:00Z"
    assert plan.output_changes["environment"].before == "staging"
    assert plan.output_changes["environment"].after == "production"
    assert plan.output_changes["app_name"].actions == ["no-op"]


def test_parse_resource_drift(drift_plan: Path) -> None:
    plan = parse_plan_file(drift_plan)
    assert len(plan.resource_drift) == 1
    drift = plan.resource_drift[0]
    assert drift.address == "local_file.config"
    assert ResourceAction.from_actions(drift.change.actions) == ResourceAction.DELETE
    assert len(plan.resource_changes) == 1
    assert plan.resource_changes[0].change.action() == ResourceAction.CREATE


@pytest.mark.parametrize(
    ("content", "exc_type"),
    [
        ("{not json", json.JSONDecodeError),
        ('{"format_version": "1.2"}', ValidationError),
    ],
)
def test_parse_failure_logs_and_reraises(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    content: str,
    exc_type: type[Exception],
) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(content)
    settings = TfDoSettings.for_testing(tmp_path)
    failure_path = settings.cache_root / PLAN_PARSE_FAILURE_FILENAME

    with pytest.raises(exc_type):
        parse_plan_file(plan_path, settings=settings)

    assert any("failed to parse plan file" in r.message for r in caplog.records)
    lines = failure_path.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["source_path"] == str(plan_path)
    assert record["error_type"] == exc_type.__name__
