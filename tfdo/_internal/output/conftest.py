from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from ask_shell._internal.rich_live import get_live, reset_live
from rich.console import Console

from tfdo._internal.output.attr_diff import compute_attr_lines
from tfdo._internal.output.models import PlanOutput
from tfdo._internal.output.parser import parse_plan_file
from tfdo._internal.output.plan_renderer import render_plan
from tfdo._internal.output.testdata_paths import TESTDATA_DIR
from tfdo._internal.output.tree_builder import ModuleNode, PlanTree, ResourceNode, build_plan_tree

REQUIRED_ATTRS_BY_TYPE: dict[str, frozenset[str]] = {
    "random_string": frozenset({"length"}),
    "random_pet": frozenset({"length", "prefix"}),
    "local_file": frozenset({"filename"}),
}


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


@pytest.fixture
def capture_console() -> Iterator[Console]:
    console = create_capture_console()
    console.begin_capture()
    get_live().console = console
    yield console
    reset_live()


@pytest.fixture
def empty_plan() -> PlanOutput:
    return PlanOutput(format_version="1.2", errored=False)


@pytest.fixture
def testdata_dir() -> Path:
    return TESTDATA_DIR


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


def _required_attrs(resource_type: str) -> frozenset[str]:
    return REQUIRED_ATTRS_BY_TYPE.get(resource_type, frozenset())


def _iter_resource_nodes(tree: PlanTree) -> list[ResourceNode]:
    nodes = list(tree.root_resources)
    nodes.extend(tree.drift)

    def walk(modules: list[ModuleNode]) -> None:
        for module in modules:
            nodes.extend(module.child_resources)
            walk(module.child_modules)

    walk(tree.modules)
    return nodes


def build_attr_lines_by_addr(tree: PlanTree) -> dict[str, list]:
    return {
        node.address: compute_attr_lines(node.change, _required_attrs(node.type)) for node in _iter_resource_nodes(tree)
    }


def render_fixture(
    path: Path | None,
    capture_console: Console,
    *,
    plan: PlanOutput | None = None,
    terminal_width: int = 120,
    show_unknown_outputs: bool = True,
) -> str:
    if plan is None:
        assert path is not None
        plan = parse_plan_file(path)
    tree = build_plan_tree(plan)
    render_plan(
        tree,
        build_attr_lines_by_addr(tree),
        terminal_width=terminal_width,
        show_unknown_outputs=show_unknown_outputs,
    )
    return capture_console.end_capture()
