from __future__ import annotations

from collections.abc import Iterator

from tfdo._internal.output.attr_diff import AttrLine, compute_attr_lines
from tfdo._internal.output.schema_lookup import RequiredAttrsLookup
from tfdo._internal.output.tree_builder import ModuleNode, PlanTree, ResourceNode


def iter_plan_resource_nodes(tree: PlanTree) -> Iterator[ResourceNode]:
    yield from tree.root_resources
    yield from tree.drift

    def walk(modules: list[ModuleNode]) -> Iterator[ResourceNode]:
        for module in modules:
            yield from module.child_resources
            yield from walk(module.child_modules)

    yield from walk(tree.modules)


def build_attr_lines_by_addr(
    tree: PlanTree,
    *,
    required_attrs: RequiredAttrsLookup,
    provider_by_addr: dict[str, str],
) -> dict[str, list[AttrLine]]:
    return {
        node.address: compute_attr_lines(
            node.change,
            required_attrs(provider_by_addr.get(node.address, ""), node.type),
        )
        for node in iter_plan_resource_nodes(tree)
    }
