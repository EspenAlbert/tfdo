from __future__ import annotations

import json
import logging

from ask_shell import console as ask_console
from pydantic import ValidationError

from tfdo._internal.core import executor
from tfdo._internal.models import PlanInput, PlanResult
from tfdo._internal.output.parser import parse_plan_file
from tfdo._internal.output.plan_artifacts import (
    atomic_write_text,
    export_plan_bin,
    plan_bin_path,
    plan_json_path,
    resolve_plan_out,
    tfdo_dir,
)
from tfdo._internal.output.plan_render_input import build_attr_lines_by_addr
from tfdo._internal.output.plan_renderer import render_plan
from tfdo._internal.output.schema_lookup import build_schema_lookups
from tfdo._internal.output.tree_builder import build_plan_tree

logger = logging.getLogger(__name__)


def run_plan(input_model: PlanInput) -> PlanResult:
    settings = input_model.settings
    if input_model.json_output:
        logger.warning("--json is ignored; tfdo renders the plan instead of raw NDJSON")

    tfdo_dir(settings.work_dir).mkdir(parents=True, exist_ok=True)
    bin_path = plan_bin_path(settings.work_dir)
    json_path = plan_json_path(settings.work_dir)

    plan_result = executor.run_streaming_plan(input_model)
    plan_exit_code = plan_result.exit_code

    if input_model.out and bin_path.is_file():
        export_plan_bin(bin_path, resolve_plan_out(settings.work_dir, input_model.out))

    if not bin_path.is_file():
        return PlanResult(exit_code=plan_exit_code, stderr=plan_result.stderr)

    plan_output, show_exit = executor.show_plan_json(settings, bin_path)
    if show_exit != 0:
        return PlanResult(exit_code=show_exit, stderr=plan_result.stderr)

    assert plan_output is not None
    atomic_write_text(json_path, json.dumps(plan_output.model_dump(mode="json"), indent=2))

    try:
        plan = parse_plan_file(json_path, settings=settings)
    except (ValidationError, json.JSONDecodeError):
        logger.error(f"failed to parse plan JSON at {json_path}")
        return PlanResult(exit_code=plan_exit_code, stderr=plan_result.stderr)

    lookups = build_schema_lookups(
        workspace_root=settings.work_dir,
        schema_cache_dir=settings.schema_cache_dir,
    )
    tree = build_plan_tree(plan)
    provider_by_addr = {rc.address: rc.provider_name or "" for rc in [*plan.resource_changes, *plan.resource_drift]}
    attr_lines = build_attr_lines_by_addr(
        tree,
        required_attrs=lookups.required_attrs,
        provider_by_addr=provider_by_addr,
    )
    console = ask_console.get_live_console()
    terminal_width = console.size.width or 120
    render_plan(
        tree,
        attr_lines,
        terminal_width=terminal_width,
        provider_by_addr=provider_by_addr,
        collection_kind=lookups.collection_kind,
    )
    return PlanResult(exit_code=plan_exit_code, stderr=plan_result.stderr)
