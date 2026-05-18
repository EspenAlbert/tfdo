from __future__ import annotations

from collections.abc import Iterator
from typing import NamedTuple

from tfdo._internal.output.attr_diff import AttrLine, compute_attr_lines
from tfdo._internal.output.schema_lookup import RequiredAttrsLookup
from tfdo._internal.output.tree_builder import ModuleNode, PlanTree, ResourceNode


class ResourceAttrLines(NamedTuple):
    planned: dict[str, list[AttrLine]]
    drift: dict[str, list[AttrLine]]


def iter_plan_resource_nodes(tree: PlanTree) -> Iterator[ResourceNode]:
    yield from tree.root_resources
    yield from tree.drift

    def walk(modules: list[ModuleNode]) -> Iterator[ResourceNode]:
        for module in modules:
            yield from module.child_resources
            yield from walk(module.child_modules)

    yield from walk(tree.modules)


def _attr_lines_for_node(
    node: ResourceNode,
    *,
    required_attrs: RequiredAttrsLookup,
    provider_by_addr: dict[str, str],
) -> list[AttrLine]:
    return compute_attr_lines(
        node.change,
        required_attrs(provider_by_addr.get(node.address, ""), node.type),
    )


def build_attr_lines_by_addr(
    tree: PlanTree,
    *,
    required_attrs: RequiredAttrsLookup,
    provider_by_addr: dict[str, str],
) -> ResourceAttrLines:
    planned: dict[str, list[AttrLine]] = {}
    drift: dict[str, list[AttrLine]] = {}
    for node in tree.drift:
        drift[node.address] = _attr_lines_for_node(
            node, required_attrs=required_attrs, provider_by_addr=provider_by_addr
        )
    for node in tree.root_resources:
        planned[node.address] = _attr_lines_for_node(
            node, required_attrs=required_attrs, provider_by_addr=provider_by_addr
        )

    def walk(modules: list[ModuleNode]) -> None:
        for module in modules:
            for node in module.child_resources:
                planned[node.address] = _attr_lines_for_node(
                    node, required_attrs=required_attrs, provider_by_addr=provider_by_addr
                )
            walk(module.child_modules)

    walk(tree.modules)
    return ResourceAttrLines(planned=planned, drift=drift)


def iter_nodes_with_attr_lines(
    tree: PlanTree, attr_lines: ResourceAttrLines
) -> Iterator[tuple[ResourceNode, list[AttrLine]]]:
    for node in tree.drift:
        yield node, attr_lines.drift.get(node.address, [])
    for node in tree.root_resources:
        yield node, attr_lines.planned.get(node.address, [])
    for module in tree.modules:
        yield from _iter_module_nodes_with_attr_lines(module, attr_lines.planned)


def _iter_module_nodes_with_attr_lines(
    module: ModuleNode, planned: dict[str, list[AttrLine]]
) -> Iterator[tuple[ResourceNode, list[AttrLine]]]:
    for node in module.child_resources:
        yield node, planned.get(node.address, [])
    for child in module.child_modules:
        yield from _iter_module_nodes_with_attr_lines(child, planned)
