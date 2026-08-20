from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from ask_shell._internal.rich_live import get_live, reset_live
from rich.console import Console

from tfdo._internal.output import plan_render_input
from tfdo._internal.output.apply_state import plan_has_applyable_changes
from tfdo._internal.output.complex_render import ComplexRenderConfig
from tfdo._internal.output.diagnostic_emitter import reset_diagnostic_seen
from tfdo._internal.output.models import PlanOutput
from tfdo._internal.output.parser import parse_plan_file
from tfdo._internal.output.plan_display import PlanDisplayOptions
from tfdo._internal.output.plan_renderer import render_plan
from tfdo._internal.output.schema_lookup import SchemaLookups, build_schema_lookups_from_index
from tfdo._internal.output.testdata_paths import TESTDATA_DIR
from tfdo._internal.output.tree_builder import PlanTree, build_plan_tree
from tfdo._internal.schema.models import ResourceSchema

REQUIRED_ATTRS_BY_TYPE: dict[str, frozenset[str]] = {
    "random_string": frozenset({"length"}),
    "random_pet": frozenset({"length", "prefix"}),
    "local_file": frozenset({"filename"}),
    "mongodbatlas_advanced_cluster": frozenset({"name", "project_id"}),
    "mongodbatlas_project": frozenset({"name"}),
    "mongodbatlas_cloud_provider_access_authorization": frozenset({"project_id"}),
    "google_storage_bucket": frozenset({"name"}),
}

SCHEMAS_DIR = TESTDATA_DIR / "schemas"


def create_capture_console(*, width: int = 120, height: int = 80) -> Console:
    return Console(
        width=width,
        height=height,
        force_terminal=True,
        legacy_windows=False,
        color_system=None,
        record=True,
        _environ={},
    )


@pytest.fixture(autouse=True)
def _reset_diagnostic_seen() -> Iterator[None]:
    reset_diagnostic_seen()
    yield
    reset_diagnostic_seen()


@pytest.fixture
def capture_console() -> Iterator[Console]:
    console = create_capture_console()
    console.begin_capture()
    live = get_live()
    prev_console = live.console
    live.console = console
    yield console
    live.console = prev_console
    console.end_capture()
    reset_live()


@pytest.fixture
def empty_plan() -> PlanOutput:
    return PlanOutput(format_version="1.2", errored=False)


@pytest.fixture
def testdata_dir() -> Path:
    return TESTDATA_DIR


@pytest.fixture
def apply_blockers_count_plan() -> Path:
    return TESTDATA_DIR / "10_apply_blockers_count.json"


@pytest.fixture
def create_flat_plan() -> Path:
    return TESTDATA_DIR / "01_create_flat.json"


@pytest.fixture
def create_modules_plan() -> Path:
    return TESTDATA_DIR / "02_create_modules.json"


@pytest.fixture
def update_plan() -> Path:
    return TESTDATA_DIR / "03_update.json"


@pytest.fixture
def destroy_plan() -> Path:
    return TESTDATA_DIR / "05_destroy.json"


@pytest.fixture
def outputs_only_plan() -> Path:
    return TESTDATA_DIR / "06_outputs_only.json"


@pytest.fixture
def replace_plan() -> Path:
    return TESTDATA_DIR / "04_replace.json"


@pytest.fixture
def drift_plan() -> Path:
    return TESTDATA_DIR / "07_drift.json"


@pytest.fixture
def cluster_resize_plan() -> Path:
    return TESTDATA_DIR / "08_cluster_resize.json"


@pytest.fixture
def create_atlas_compact_plan() -> Path:
    return TESTDATA_DIR / "09_create_atlas_compact.json"


def _load_fixture_schemas() -> dict[str, ResourceSchema]:
    index: dict[str, ResourceSchema] = {}
    if not SCHEMAS_DIR.is_dir():
        return index
    for path in SCHEMAS_DIR.glob("*.json"):
        raw = json.loads(path.read_text())
        index[path.stem] = ResourceSchema.model_validate(raw)
    return index


@pytest.fixture
def fixture_schema_lookups() -> SchemaLookups:
    return build_schema_lookups_from_index(_load_fixture_schemas())


def _required_attrs(_provider: str, resource_type: str) -> frozenset[str]:
    return REQUIRED_ATTRS_BY_TYPE.get(resource_type, frozenset())


def _provider_by_addr(plan: PlanOutput) -> dict[str, str]:
    return {rc.address: rc.provider_name or "" for rc in [*plan.resource_changes, *plan.resource_drift]}


def build_attr_lines_by_addr(
    tree: PlanTree,
    *,
    plan: PlanOutput,
    schema_lookups: SchemaLookups | None = None,
    show_create_defaults: bool = False,
) -> plan_render_input.ResourceAttrLines:
    provider_by_addr = _provider_by_addr(plan)

    def required_attrs(provider: str, resource_type: str) -> frozenset[str]:
        if schema_lookups is not None:
            from_schema = schema_lookups.required_attrs(provider, resource_type)
            if from_schema:
                return from_schema
        return REQUIRED_ATTRS_BY_TYPE.get(resource_type, frozenset())

    return plan_render_input.build_attr_lines_by_addr(
        tree,
        required_attrs=required_attrs,
        provider_by_addr=provider_by_addr,
        show_create_defaults=show_create_defaults,
    )


def render_fixture(
    path: Path | None,
    capture_console: Console,
    *,
    plan: PlanOutput | None = None,
    terminal_width: int = 120,
    show_unknown_outputs: bool = True,
    plan_display: PlanDisplayOptions | None = None,
    schema_lookups: SchemaLookups | None = None,
) -> str:
    if plan is None:
        assert path is not None
        plan = parse_plan_file(path)
    tree = build_plan_tree(plan)
    provider_by_addr = _provider_by_addr(plan)
    lookups = schema_lookups or build_schema_lookups_from_index(_load_fixture_schemas())
    display = plan_display or PlanDisplayOptions()
    render_plan(
        tree,
        build_attr_lines_by_addr(
            tree,
            plan=plan,
            schema_lookups=lookups,
            show_create_defaults=display.show_create_defaults,
        ),
        terminal_width=terminal_width,
        provider_by_addr=provider_by_addr,
        collection_kind=lookups.collection_kind,
        computed_at_path=lookups.computed_at_path,
        resource_schema=lookups.resource_schema,
        complex_config=ComplexRenderConfig(max_structural_lines=display.max_inline_lines),
        show_unknown_outputs=show_unknown_outputs,
        plan_display=display,
        has_applyable_changes=plan_has_applyable_changes(plan),
    )
    return capture_console.end_capture()
