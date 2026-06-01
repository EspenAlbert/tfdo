from __future__ import annotations

import json
import logging

from ask_shell import console as ask_console
from pydantic import ValidationError

from tfdo._internal.core import failure_output, plan_subprocess
from tfdo._internal.core.lifecycle_footer import print_lifecycle_footer
from tfdo._internal.hcl_read import find_lock_file
from tfdo._internal.models import PlanInput, PlanResult
from tfdo._internal.output.apply_state import plan_has_applyable_changes
from tfdo._internal.output.complex_render import ComplexRenderConfig
from tfdo._internal.output.parser import parse_plan_file
from tfdo._internal.output.plan_artifacts import (
    atomic_write_text,
    begin_lifecycle_debug_log,
    export_plan_bin,
    plan_bin_path,
    plan_json_path,
    resolve_plan_out,
    tfdo_dir,
)
from tfdo._internal.output.plan_display import detail_preset, merge_plan_display
from tfdo._internal.output.plan_render_input import build_attr_lines_by_addr
from tfdo._internal.output.plan_renderer import render_plan
from tfdo._internal.output.schema_lookup import build_schema_lookups
from tfdo._internal.output.tree_builder import build_plan_tree
from tfdo._internal.run.run_dir_summary import output_change_count_from_plan_tree, resource_counts_from_plan_tree
from tfdo._internal.schema.plan_warm import warm_plan_schema_cache
from tfdo._internal.settings import load_user_config

logger = logging.getLogger(__name__)

_PARSE_FAILURE_MESSAGE = "tfdo failed to parse plan JSON (see Plan JSON path in footer)"


def _plan_command_label(input_model: PlanInput) -> str:
    return "destroy plan" if input_model.destroy_plan else "plan"


def _exit_plan(
    input_model: PlanInput,
    result: PlanResult,
    *,
    report: bool = True,
    message: str | None = None,
) -> PlanResult:
    if report:
        failure_output.report_lifecycle_failure(
            command=_plan_command_label(input_model),
            exit_code=result.exit_code,
            stderr=result.stderr,
            message=message,
            diagnostics_already_shown=result.diagnostics_emitted,
        )
    print_lifecycle_footer(input_model.settings, detail=input_model.detail)
    return result


def plan_and_render(input_model: PlanInput) -> PlanResult:
    settings = input_model.settings
    tfdo_dir(settings.work_dir).mkdir(parents=True, exist_ok=True)
    begin_lifecycle_debug_log(settings.work_dir)
    bin_path = plan_bin_path(settings.work_dir)
    json_path = plan_json_path(settings.work_dir)

    plan_result = plan_subprocess.run_streaming_plan(input_model)
    plan_exit_code = plan_result.exit_code

    if failure_output.is_plan_hard_failure(plan_exit_code):
        return _exit_plan(input_model, plan_result)

    if not bin_path.is_file():
        return _exit_plan(input_model, plan_result, report=plan_exit_code != 0)

    show_result = plan_subprocess.show_plan_json(settings, bin_path)
    if show_result.exit_code != 0:
        show_plan_result = PlanResult(exit_code=show_result.exit_code, stderr=plan_result.stderr)
        return _exit_plan(input_model, show_plan_result)

    plan_output = show_result.plan_output
    raw_plan_json = show_result.raw_json
    assert plan_output is not None
    assert raw_plan_json is not None
    atomic_write_text(json_path, json.dumps(json.loads(raw_plan_json), indent=2))

    try:
        plan = parse_plan_file(json_path, settings=settings)
    except (ValidationError, json.JSONDecodeError):
        logger.error(f"failed to parse plan JSON at {json_path}")
        parse_result = PlanResult(exit_code=plan_exit_code, stderr=plan_result.stderr)
        return _exit_plan(input_model, parse_result, message=_PARSE_FAILURE_MESSAGE)

    lock_path = find_lock_file(settings.work_dir)
    if lock_path is not None:
        warm_plan_schema_cache(
            settings,
            lock_path=lock_path,
            plan=plan,
            schema_cache_dir=settings.schema_cache_dir,
        )
    lookups = build_schema_lookups(
        workspace_root=settings.work_dir,
        schema_cache_dir=settings.schema_cache_dir,
    )
    user_config = load_user_config(settings)
    plan_display = merge_plan_display(
        detail_preset(input_model.detail),
        user_config.plan_display,
        input_model.plan_display_cli,
    )
    tree = build_plan_tree(plan)
    plan_counts = resource_counts_from_plan_tree(tree)
    plan_output_changes = output_change_count_from_plan_tree(tree)
    applyable = plan_has_applyable_changes(plan)
    provider_by_addr = {rc.address: rc.provider_name or "" for rc in [*plan.resource_changes, *plan.resource_drift]}
    attr_lines = build_attr_lines_by_addr(
        tree,
        required_attrs=lookups.required_attrs,
        provider_by_addr=provider_by_addr,
        show_create_defaults=plan_display.show_create_defaults,
    )
    console = ask_console.get_live_console()
    terminal_width = console.size.width or 120
    render_plan(
        tree,
        attr_lines,
        terminal_width=terminal_width,
        provider_by_addr=provider_by_addr,
        collection_kind=lookups.collection_kind,
        computed_at_path=lookups.computed_at_path,
        resource_schema=lookups.resource_schema,
        complex_config=ComplexRenderConfig(max_structural_lines=plan_display.max_inline_lines),
        plan_display=plan_display,
        has_applyable_changes=applyable,
    )
    return _exit_plan(
        input_model,
        PlanResult(
            exit_code=plan_exit_code,
            stderr=plan_result.stderr,
            has_applyable_changes=applyable,
            resource_counts=plan_counts,
            output_change_count=plan_output_changes,
        ),
        report=False,
    )


def run_plan(input_model: PlanInput) -> PlanResult:
    if input_model.json_output:
        logger.warning("--json is ignored; tfdo renders the plan instead of raw NDJSON")

    result = plan_and_render(input_model)
    if input_model.out:
        bin_path = plan_bin_path(input_model.settings.work_dir)
        if bin_path.is_file():
            export_plan_bin(bin_path, resolve_plan_out(input_model.settings.work_dir, input_model.out))
    return result
