from __future__ import annotations

from pathlib import Path

from tfdo._internal.output.conftest import render_fixture
from tfdo._internal.output.models import Change, PlanOutput, ResourceChange


def test_create_flat(create_flat_plan: Path, capture_console) -> None:
    rendered = render_fixture(create_flat_plan, capture_console)
    assert "📋 Plan: 🟢 3 to add" in rendered
    assert "🟢 local_file.config" in rendered
    assert "🟢 random_pet.server" in rendered
    assert "🟢 random_string.suffix" in rendered
    assert 'filename: "./output/app.conf"' in rendered
    assert "     + file_permission:" in rendered
    assert "⚠️ Drift:" not in rendered


def test_long_scalar_splits_old_new_at_arrow(update_plan: Path, capture_console) -> None:
    rendered = render_fixture(update_plan, capture_console)
    lines = rendered.splitlines()
    content_i = next(i for i, line in enumerate(lines) if line.startswith("     ! content:"))
    assert lines[content_i + 1].startswith("     -> ")


def test_drift_before_plan_header(drift_plan: Path, capture_console) -> None:
    rendered = render_fixture(drift_plan, capture_console)
    drift_idx = rendered.index("⚠️ Drift:")
    header_idx = rendered.index("📋 Plan:")
    assert drift_idx < header_idx
    assert "⚠️ local_file.config" in rendered
    assert "🟢 local_file.config" in rendered


def test_destroy_with_required_context(destroy_plan: Path, capture_console) -> None:
    rendered = render_fixture(destroy_plan, capture_console)
    assert "🔴 4 to destroy" in rendered
    assert '       prefix: "db"' in rendered
    assert "⚠️  This plan will destroy all 4 resources" in rendered


def test_outputs_only(outputs_only_plan: Path, capture_console) -> None:
    rendered = render_fixture(outputs_only_plan, capture_console)
    assert "📋 Plan: no resource changes" in rendered
    assert "📤 Outputs" in rendered
    assert "🟢 1 new" in rendered
    assert "🟡 2 changed" in rendered
    assert "  + deployed_at:" in rendered
    assert "  ~ environment:" in rendered


def test_empty_plan(empty_plan, capture_console) -> None:
    rendered = render_fixture(None, capture_console, plan=empty_plan)
    assert "✅ Plan: no changes" in rendered
    assert "Infrastructure matches configuration." in rendered


def test_destroy_warning_partial(capture_console) -> None:
    changes = [
        *[
            ResourceChange(
                address=f"random_pet.r{i}",
                mode="managed",
                type="random_pet",
                name=f"r{i}",
                change=Change(actions=["delete"]),
            )
            for i in range(4)
        ],
        ResourceChange(
            address="random_pet.keep",
            mode="managed",
            type="random_pet",
            name="keep",
            change=Change(actions=["create"], after={"length": 2}),
        ),
    ]
    plan = PlanOutput(format_version="1.2", errored=False, resource_changes=changes)
    rendered = render_fixture(None, capture_console, plan=plan)
    assert "⚠️  This plan will destroy 4 resources" in rendered
    assert "destroy all" not in rendered


def test_repeated_header_for_long_plan(capture_console) -> None:
    changes = [
        ResourceChange(
            address=f"random_pet.r{i}",
            mode="managed",
            type="random_pet",
            name=f"r{i}",
            change=Change(
                actions=["create"],
                after={"length": 2, "prefix": "x", "id": f"id{i}"},
            ),
        )
        for i in range(20)
    ]
    plan = PlanOutput(format_version="1.2", errored=False, resource_changes=changes)
    rendered = render_fixture(None, capture_console, plan=plan)
    assert rendered.count("📋 Plan:") == 2
