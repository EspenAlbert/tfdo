from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from ask_shell import console as ask_console
from rich.console import Console
from rich.segment import Segment

from tfdo._internal.output.apply_state import plan_has_applyable_changes
from tfdo._internal.output.complex_render import ComplexRenderConfig
from tfdo._internal.output.conftest import build_attr_lines_by_addr, render_fixture
from tfdo._internal.output.models import Change, OutputChange, PlanOutput, ResourceChange
from tfdo._internal.output.parser import parse_plan_file
from tfdo._internal.output.plan_display import PlanDisplayOptions
from tfdo._internal.output.plan_renderer import (
    _action_counts,
    _build_complex_results,
    _build_module_tree,
    _filter_attr_lines_by_addr,
    _format_output_section,
    _module_depth_by_address,
    _plan_header_line,
    render_plan,
)
from tfdo._internal.output.tree_builder import build_plan_tree


def test_module_resource_header_not_dim(create_modules_plan: Path) -> None:
    plan = parse_plan_file(create_modules_plan)
    tree = build_plan_tree(plan)
    attr_lines = build_attr_lines_by_addr(tree, plan=plan)
    complex_results = _build_complex_results(
        tree,
        attr_lines,
        terminal_width=120,
        config=ComplexRenderConfig(),
        providers={},
        collection_kind=None,
        lookup=lambda _p, _t, _path: None,
        show_computed_deltas=False,
        show_full_config_annex=False,
        show_create_defaults=False,
        show_json_annex=False,
        resource_schema=None,
    )
    renderable = _build_module_tree(
        tree.modules[0],
        attr_lines.planned,
        complex_results=complex_results,
        terminal_width=120,
        module_depths=_module_depth_by_address(tree),
    )
    console = Console(width=120, force_terminal=True, color_system="standard", legacy_windows=False)
    for seg in console.render(renderable):
        if not isinstance(seg, Segment):
            continue
        if "module.networking.local_file.network_config" not in seg.text:
            continue
        assert seg.style is not None
        assert not seg.style.dim
        assert seg.style.color is not None
        assert seg.style.color.name == "green"
        return
    pytest.fail("module resource header segment not found")


def test_module_attr_lines_not_green(create_modules_plan: Path) -> None:
    plan = parse_plan_file(create_modules_plan)
    tree = build_plan_tree(plan)
    attr_lines = build_attr_lines_by_addr(tree, plan=plan)
    complex_results = _build_complex_results(
        tree,
        attr_lines,
        terminal_width=120,
        config=ComplexRenderConfig(),
        providers={},
        collection_kind=None,
        lookup=lambda _p, _t, _path: None,
        show_computed_deltas=False,
        show_full_config_annex=False,
        show_create_defaults=False,
        show_json_annex=False,
        resource_schema=None,
    )
    renderable = _build_module_tree(
        tree.modules[0],
        attr_lines.planned,
        complex_results=complex_results,
        terminal_width=120,
        module_depths=_module_depth_by_address(tree),
    )
    console = Console(width=120, force_terminal=True, color_system="standard", legacy_windows=False)
    for seg in console.render(renderable):
        if not isinstance(seg, Segment):
            continue
        if "directory_permission" in seg.text:
            assert seg.style is not None
            assert seg.style.color is None
            return
    pytest.fail("module attribute segment not found")


def test_compact_create_hides_empty_attrs(capture_console) -> None:
    plan = PlanOutput(
        format_version="1.2",
        errored=False,
        resource_changes=[
            ResourceChange(
                address="module.project.mongodbatlas_project.this",
                mode="managed",
                type="mongodbatlas_project",
                name="this",
                module_address="module.project",
                change=Change(
                    actions=["create"],
                    after={
                        "name": "project-module-online",
                        "tags": {},
                        "teams": [],
                        "limits": [],
                    },
                ),
            ),
        ],
    )
    rendered = render_fixture(None, capture_console, plan=plan, terminal_width=120)
    assert "+ tags:" not in rendered
    assert "+ teams:" not in rendered

    console = capture_console
    console.begin_capture()
    verbose = render_fixture(
        None,
        console,
        plan=plan,
        terminal_width=120,
        plan_display=PlanDisplayOptions(show_create_defaults=True),
    )
    assert "+ tags: {}" in verbose


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


def test_drift_create_same_address_keeps_planned_attrs(drift_plan: Path) -> None:
    plan = parse_plan_file(drift_plan)
    tree = build_plan_tree(plan)
    providers = {rc.address: rc.provider_name or "" for rc in [*plan.resource_changes, *plan.resource_drift]}
    raw = build_attr_lines_by_addr(tree, plan=plan)
    filtered = _filter_attr_lines_by_addr(
        tree,
        raw,
        providers,
        lookup=lambda _p, _t, _path: None,
        show_computed_deltas=False,
        terminal_width=120,
        inline_min_width=120,
    )
    planned_lines = filtered.planned["local_file.config"]
    assert planned_lines
    assert any(line.name == "filename" for line in planned_lines)


def test_drift_after_plan_header(drift_plan: Path, capture_console) -> None:
    rendered = render_fixture(drift_plan, capture_console)
    drift_idx = rendered.index("⚠️ Drift:")
    header_idx = rendered.index("📋 Plan:")
    assert header_idx < drift_idx
    assert "⚠️ local_file.config" in rendered
    assert "🟢 local_file.config" in rendered
    assert 'filename: "./output/config.json"' in rendered


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


def test_drift_only_no_planned_changes_header() -> None:
    plan = PlanOutput(
        format_version="1.2",
        errored=False,
        resource_changes=[
            ResourceChange(
                address="local_file.config",
                mode="managed",
                type="local_file",
                name="config",
                change=Change(actions=["no-op"]),
            )
        ],
        resource_drift=[
            ResourceChange(
                address="local_file.config",
                mode="managed",
                type="local_file",
                name="config",
                change=Change(actions=["delete"]),
            )
        ],
    )
    tree = build_plan_tree(plan)
    header = _plan_header_line(tree, _action_counts(tree), has_applyable_changes=plan_has_applyable_changes(plan))
    assert header.line == "✅ Plan: no changes"
    assert header.render_body


def test_not_applyable_header_uses_checkmark() -> None:
    plan = PlanOutput(
        format_version="1.2",
        errored=False,
        applyable=False,
        output_changes={
            "deployed_at": OutputChange(
                actions=["create"],
                before=None,
                after="2026-05-18T19:00:00Z",
            )
        },
    )
    tree = build_plan_tree(plan)
    header = _plan_header_line(tree, _action_counts(tree), has_applyable_changes=plan_has_applyable_changes(plan))
    assert header.line == "✅ Plan: no changes"


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


def test_long_create_scalar_splits_value_line(capture_console) -> None:
    plan = PlanOutput(
        format_version="1.2",
        errored=False,
        resource_changes=[
            ResourceChange(
                address="random_pet.long",
                mode="managed",
                type="random_pet",
                name="long",
                change=Change(actions=["create"], after={"url": "https://example.com/" + "x" * 80}),
            )
        ],
    )
    rendered = render_fixture(None, capture_console, plan=plan, terminal_width=60)
    lines = rendered.splitlines()
    url_i = next(i for i, line in enumerate(lines) if "+ url:" in line)
    assert lines[url_i + 1].strip().startswith('"https://')


def test_long_output_splits_across_lines() -> None:
    wide = {f"id{i}": f"project-{i}" * 8 for i in range(12)}
    lines = _format_output_section(
        {"project_ids": OutputChange(actions=["create"], after=wide)},
        terminal_width=80,
        show_unknown_outputs=True,
    )
    assert any(line.strip().startswith("+ project_ids:") for line in lines)
    assert any(line.startswith("    ") and "id0" in line for line in lines)


def test_output_wraps_on_wide_terminal() -> None:
    project_ids = {
        "66ed369a0499a2537e7fdea0": "espen-qa",
        "6788f68b73f7f504323c1b6c": "test-acc-tf-p-5442058431446053086",
        "6788f69f348f017dcf29dd8a": "test-acc-tf-p-3054099010026082690",
        "68b535c1b41711692503d19f": "byok-ff-enabled",
        "6a074e6c308ccc31d5b24875": "dev",
        "6a0832efa4cbef75d687611d": "prod",
    }
    lines = _format_output_section(
        {"project_ids": OutputChange(actions=["create"], after=project_ids)},
        terminal_width=300,
        show_unknown_outputs=True,
    )
    assert any(line.strip() == "+ project_ids:" for line in lines)
    assert sum(1 for line in lines if '"66ed369a0499a2537e7fdea0"' in line) == 1
    assert sum(1 for line in lines if line.strip().startswith('"6')) >= 2


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


def test_header_only_prefixes_run_dir(create_flat_plan: Path) -> None:
    plan = parse_plan_file(create_flat_plan)
    tree = build_plan_tree(plan)
    printed: list[object] = []

    with patch.object(ask_console, "print_to_live", side_effect=lambda *args, **_kw: printed.extend(args)):
        render_plan(
            tree,
            build_attr_lines_by_addr(tree, plan=plan),
            terminal_width=120,
            header_only=True,
            run_dir_key="envs/staging/compute",
        )

    assert any(str(line).startswith("envs/staging/compute: 📋 Plan:") for line in printed)
