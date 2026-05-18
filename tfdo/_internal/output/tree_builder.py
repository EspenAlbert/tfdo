from __future__ import annotations

from functools import total_ordering

from pydantic import BaseModel, ConfigDict, Field

from tfdo._internal.output.models import (
    Change,
    OutputChange,
    PlanOutput,
    ResourceAction,
    ResourceChange,
)


@total_ordering
class ResourceNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    address: str
    type: str
    name: str
    mode: str
    action: ResourceAction
    change: Change
    index: int | str | None = None
    action_reason: str | None = None

    @classmethod
    def from_resource_change(cls, rc: ResourceChange) -> ResourceNode:
        return cls(
            address=rc.address,
            type=rc.type,
            name=rc.name,
            mode=rc.mode,
            action=rc.change.action(),
            change=rc.change,
            index=rc.index,
            action_reason=rc.action_reason,
        )

    def __lt__(self, other: object) -> bool:
        match other:
            case ResourceNode():
                return (self.action, self.address) < (other.action, other.address)
            case _:
                return NotImplemented


@total_ordering
class ModuleNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    child_modules: list[ModuleNode] = Field(default_factory=list)
    child_resources: list[ResourceNode] = Field(default_factory=list)

    def __lt__(self, other: object) -> bool:
        match other:
            case ModuleNode():
                return self.name < other.name
            case _:
                return NotImplemented


class PlanTree(BaseModel):
    model_config = ConfigDict(extra="ignore")

    root_resources: list[ResourceNode] = Field(default_factory=list)
    modules: list[ModuleNode] = Field(default_factory=list)
    drift: list[ResourceNode] = Field(default_factory=list)
    output_changes: dict[str, OutputChange] = Field(default_factory=dict)


class _ModuleAcc:
    __slots__ = ("resources", "children")

    def __init__(self) -> None:
        self.resources: list[ResourceChange] = []
        self.children: dict[str, _ModuleAcc] = {}


def module_name_segments(module_address: str) -> list[str]:
    parts = module_address.split(".")
    segments: list[str] = []
    i = 0
    while i < len(parts):
        if parts[i] == "module" and i + 1 < len(parts):
            segments.append(parts[i + 1])
            i += 2
        else:
            i += 1
    return segments


def _sort_resources(nodes: list[ResourceNode]) -> list[ResourceNode]:
    return sorted(nodes)


def _collapse_module(node: ModuleNode) -> ModuleNode:
    node.child_modules = [_collapse_module(c) for c in node.child_modules]
    while len(node.child_modules) == 1 and not node.child_resources:
        child = node.child_modules[0]
        node.name = f"{node.name} > {child.name}"
        node.child_modules = child.child_modules
        node.child_resources = child.child_resources
    return node


def _sort_module(node: ModuleNode) -> ModuleNode:
    node.child_resources = _sort_resources(node.child_resources)
    node.child_modules = sorted(_sort_module(c) for c in node.child_modules)
    return node


def _to_module_node(name: str, acc: _ModuleAcc) -> ModuleNode:
    return ModuleNode(
        name=name,
        child_resources=[ResourceNode.from_resource_change(r) for r in acc.resources],
        child_modules=[_to_module_node(child_name, child_acc) for child_name, child_acc in acc.children.items()],
    )


def _insert_resource(
    root_resources: list[ResourceChange],
    top_modules: dict[str, _ModuleAcc],
    rc: ResourceChange,
) -> None:
    segments = module_name_segments(rc.module_address or "")
    if not segments:
        root_resources.append(rc)
        return
    acc = top_modules.setdefault(segments[0], _ModuleAcc())
    for seg in segments[1:]:
        acc = acc.children.setdefault(seg, _ModuleAcc())
    acc.resources.append(rc)


def build_plan_tree(plan: PlanOutput) -> PlanTree:
    root_rcs: list[ResourceChange] = []
    top_modules: dict[str, _ModuleAcc] = {}
    for rc in plan.resource_changes:
        action = rc.change.action()
        if action in (ResourceAction.NO_OP, ResourceAction.READ):
            continue
        _insert_resource(root_rcs, top_modules, rc)

    root_resources = _sort_resources([ResourceNode.from_resource_change(rc) for rc in root_rcs])
    modules = [_sort_module(_collapse_module(_to_module_node(name, acc))) for name, acc in sorted(top_modules.items())]
    drift = _sort_resources([ResourceNode.from_resource_change(rc) for rc in plan.resource_drift])
    return PlanTree(
        root_resources=root_resources,
        modules=modules,
        drift=drift,
        output_changes=dict(plan.output_changes),
    )
