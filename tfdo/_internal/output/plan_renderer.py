from __future__ import annotations

import json
from typing import NamedTuple, cast

from ask_shell import console as ask_console
from rich.console import RenderableType
from rich.text import Text
from rich.tree import Tree

from tfdo._internal.output import display_path
from tfdo._internal.output.attr_diff import AttrLine, AttrPrefix, ValueKind
from tfdo._internal.output.complex_render import (
    ComplexRenderConfig,
    ComplexRenderResult,
    DetailBlock,
    render_complex_value,
)
from tfdo._internal.output.models import Change, OutputChange, ResourceAction
from tfdo._internal.output.plan_display import PlanDisplayOptions
from tfdo._internal.output.plan_filters import (
    ComputedOnlyLookup,
    filter_attr_lines,
    is_computed_only_drift_resource,
    is_computed_only_plan_delta,
)
from tfdo._internal.output.plan_render_input import ResourceAttrLines, iter_nodes_with_attr_lines
from tfdo._internal.output.render_thresholds import (
    OUTPUT_MULTILINE_CHARS,
    OUTPUT_PRETTY_JSON_CHARS,
    OUTPUT_WRAP_WIDTH,
    TREE_BASE_PREFIX_CHARS,
    TREE_GUIDE_CHARS_PER_LEVEL,
)
from tfdo._internal.output.schema_lookup import CollectionKindLookup
from tfdo._internal.output.tree_builder import ModuleNode, PlanTree, ResourceNode

ATTR_CONTEXT_INDENT = 7
ATTR_CHANGED_INDENT = 5
MODULE_TREE_ATTR_INDENT = 0
ATTR_VALUE_INDENT = 7
OUTPUT_INDENT = 2
LINE_REPEAT_THRESHOLD = 40
DESTROY_WARNING_THRESHOLD = 3
_MODULE_TREE_LABEL_STYLE = "bold"
_MODULE_TREE_GUIDE_STYLE = "dim"

_REPLACE_ACTIONS = frozenset({ResourceAction.REPLACE_DESTROY_FIRST, ResourceAction.REPLACE_CREATE_FIRST})
_SENSITIVE = "(sensitive)"
_KNOWN_AFTER_APPLY = "(known after apply)"


class PlanActionCounts(NamedTuple):
    add: int
    change: int
    destroy: int
    replace: int
    total: int


class _PlanHeader(NamedTuple):
    line: str
    subtitle: str | None = None
    render_body: bool = True


class _ComplexKey(NamedTuple):
    address: str
    attr_name: str


class _PrintState:
    __slots__ = ("lines",)

    def __init__(self) -> None:
        self.lines = 0

    def emit(self, *objects: object, style: str | None = None) -> None:
        ask_console.print_to_live(*objects, style=style)
        self.lines += 1

    def emit_renderable(self, renderable: RenderableType) -> None:
        console = ask_console.get_live_console()
        self.lines += len(console.render_lines(renderable))
        ask_console.print_to_live(renderable)

    def blank(self) -> None:
        self.emit("")


def render_plan(
    tree: PlanTree,
    attr_lines: ResourceAttrLines,
    *,
    terminal_width: int,
    provider_by_addr: dict[str, str] | None = None,
    collection_kind: CollectionKindLookup | None = None,
    computed_at_path: ComputedOnlyLookup | None = None,
    complex_config: ComplexRenderConfig | None = None,
    show_unknown_outputs: bool = True,
    plan_display: PlanDisplayOptions | None = None,
) -> None:
    display = plan_display or PlanDisplayOptions()
    config = complex_config or ComplexRenderConfig()
    lookup = computed_at_path or (lambda _p, _t, _path: None)
    filtered = _filter_attr_lines_by_addr(
        tree,
        attr_lines,
        provider_by_addr or {},
        lookup=lookup,
        show_computed_deltas=display.show_computed_deltas,
    )
    complex_results = _build_complex_results(
        tree,
        filtered,
        terminal_width=terminal_width,
        config=config,
        providers=provider_by_addr or {},
        collection_kind=collection_kind,
        lookup=lookup,
        show_computed_deltas=display.show_computed_deltas,
        show_full_config_annex=display.show_full_config_annex,
        show_create_defaults=display.show_create_defaults,
    )
    state = _PrintState()
    if display.show_full_config_annex:
        _print_detail_blocks(state, _collect_detail_blocks(complex_results))

    header = _plan_header_line(tree, _action_counts(tree))
    state.emit(header.line)
    if header.subtitle:
        state.emit(header.subtitle, style="dim")
    if not header.render_body:
        return

    state.blank()
    _print_destroy_warning(state, tree)
    _print_drift(
        state,
        tree,
        filtered.drift,
        complex_results,
        terminal_width,
        provider_by_addr=provider_by_addr or {},
        lookup=lookup,
        show_computed_drift=display.show_computed_drift,
    )
    _print_resources(state, tree, filtered.planned, complex_results, terminal_width)
    _print_outputs(
        state,
        tree.output_changes,
        terminal_width=terminal_width,
        show_unknown_outputs=show_unknown_outputs,
    )
    _maybe_repeat_header(state, header.line)


def _print_detail_blocks(state: _PrintState, detail_blocks: list[DetailBlock]) -> None:
    if not detail_blocks:
        return
    for block in detail_blocks:
        for line in block.body_lines:
            state.emit(line)
    state.blank()


def _print_drift(
    state: _PrintState,
    tree: PlanTree,
    drift_attr_lines: dict[str, list[AttrLine]],
    complex_results: dict[_ComplexKey, ComplexRenderResult],
    terminal_width: int,
    *,
    provider_by_addr: dict[str, str],
    lookup: ComputedOnlyLookup,
    show_computed_drift: bool,
) -> None:
    drift_lines = _drift_section(
        tree,
        drift_attr_lines,
        complex_results=complex_results,
        terminal_width=terminal_width,
        provider_by_addr=provider_by_addr,
        lookup=lookup,
        show_computed_drift=show_computed_drift,
    )
    if not drift_lines:
        return
    for line in drift_lines:
        state.emit(line)
    state.blank()


def _print_destroy_warning(state: _PrintState, tree: PlanTree) -> None:
    if warning := _destroy_warning_line(_action_counts(tree)):
        state.emit(warning)
        state.blank()


def _print_resources(
    state: _PrintState,
    tree: PlanTree,
    attr_lines_by_addr: dict[str, list[AttrLine]],
    complex_results: dict[_ComplexKey, ComplexRenderResult],
    terminal_width: int,
) -> None:
    depths = _module_depth_by_address(tree)
    for node in tree.root_resources:
        state.emit(_format_resource_header(node))
        for line in _resource_attr_lines(
            node,
            attr_lines_by_addr.get(node.address, []),
            complex_results=complex_results,
            terminal_width=terminal_width,
            tree_extra_prefix=0,
        ):
            state.emit(line)

    for module in tree.modules:
        state.emit_renderable(
            _build_module_tree(
                module,
                attr_lines_by_addr,
                complex_results=complex_results,
                terminal_width=terminal_width,
                module_depths=depths,
            )
        )


def _print_outputs(
    state: _PrintState,
    output_changes: dict[str, OutputChange],
    *,
    terminal_width: int,
    show_unknown_outputs: bool,
) -> None:
    output_lines = _format_output_section(
        output_changes,
        terminal_width=terminal_width,
        show_unknown_outputs=show_unknown_outputs,
    )
    if not output_lines:
        return
    state.blank()
    for line in output_lines:
        state.emit(line)


def _maybe_repeat_header(state: _PrintState, header: str) -> None:
    if state.lines <= LINE_REPEAT_THRESHOLD:
        return
    state.blank()
    state.emit(header)


def _action_counts(tree: PlanTree) -> PlanActionCounts:
    add = change = destroy = replace = 0

    def count_node(node: ResourceNode) -> None:
        nonlocal add, change, destroy, replace
        match node.action:
            case ResourceAction.CREATE:
                add += 1
            case ResourceAction.UPDATE:
                change += 1
            case ResourceAction.DELETE:
                destroy += 1
            case ResourceAction.REPLACE_DESTROY_FIRST | ResourceAction.REPLACE_CREATE_FIRST:
                replace += 1
            case _:
                pass

    for node in tree.root_resources:
        count_node(node)

    def walk_modules(modules: list[ModuleNode]) -> None:
        for module in modules:
            for node in module.child_resources:
                count_node(node)
            walk_modules(module.child_modules)

    walk_modules(tree.modules)
    total = add + change + destroy + replace
    return PlanActionCounts(add=add, change=change, destroy=destroy, replace=replace, total=total)


def _plan_header_line(tree: PlanTree, counts: PlanActionCounts) -> _PlanHeader:
    if not _has_resources(tree) and not tree.output_changes:
        return _PlanHeader(
            line="✅ Plan: no changes",
            subtitle="Infrastructure matches configuration.",
            render_body=False,
        )
    if not _has_resources(tree):
        return _PlanHeader(line="📋 Plan: no resource changes")
    parts: list[str] = []
    if counts.add:
        parts.append(f"🟢 {counts.add} to add")
    if counts.change:
        parts.append(f"🟡 {counts.change} to change")
    if counts.destroy:
        parts.append(f"🔴 {counts.destroy} to destroy")
    if counts.replace:
        parts.append(f"🟣 {counts.replace} to replace")
    return _PlanHeader(line=f"📋 Plan: {', '.join(parts)}")


def _destroy_warning_line(counts: PlanActionCounts) -> str | None:
    if counts.destroy <= 0:
        return None
    if counts.destroy == counts.total:
        return f"⚠️  This plan will destroy all {counts.destroy} resources"
    if counts.destroy > DESTROY_WARNING_THRESHOLD:
        return f"⚠️  This plan will destroy {counts.destroy} resources"
    return None


def _has_resources(tree: PlanTree) -> bool:
    if tree.root_resources or tree.drift:
        return True
    return any(_module_has_resources(module) for module in tree.modules)


def _module_has_resources(module: ModuleNode) -> bool:
    if module.child_resources:
        return True
    return any(_module_has_resources(child) for child in module.child_modules)


def _iter_all_resources(tree: PlanTree) -> list[ResourceNode]:
    nodes = list(tree.root_resources)
    nodes.extend(tree.drift)

    def walk(modules: list[ModuleNode]) -> None:
        for module in modules:
            nodes.extend(module.child_resources)
            walk(module.child_modules)

    walk(tree.modules)
    return nodes


def _module_depth_by_address(tree: PlanTree) -> dict[str, int]:
    depths: dict[str, int] = {node.address: 0 for node in tree.root_resources}
    depths.update({node.address: 0 for node in tree.drift})

    def walk(modules: list[ModuleNode], depth: int) -> None:
        for module in modules:
            for node in module.child_resources:
                depths[node.address] = depth
            walk(module.child_modules, depth + 1)

    walk(tree.modules, 1)
    return depths


def _tree_extra_prefix(module_depth: int) -> int:
    if module_depth <= 0:
        return 0
    return TREE_BASE_PREFIX_CHARS + (module_depth - 1) * TREE_GUIDE_CHARS_PER_LEVEL


def _filter_attr_lines_by_addr(
    tree: PlanTree,
    attr_lines: ResourceAttrLines,
    providers: dict[str, str],
    *,
    lookup: ComputedOnlyLookup,
    show_computed_deltas: bool,
) -> ResourceAttrLines:
    planned: dict[str, list[AttrLine]] = {}
    drift: dict[str, list[AttrLine]] = {}

    def store_filtered(node: ResourceNode, lines: list[AttrLine], dest: dict[str, list[AttrLine]]) -> None:
        dest[node.address] = filter_attr_lines(
            lines,
            change=node.change,
            lookup=lookup,
            provider=providers.get(node.address, ""),
            resource_type=node.type,
            show_computed_deltas=show_computed_deltas,
        )

    for node in tree.drift:
        store_filtered(node, attr_lines.drift.get(node.address, []), drift)
    for node in tree.root_resources:
        store_filtered(node, attr_lines.planned.get(node.address, []), planned)

    def walk(modules: list[ModuleNode]) -> None:
        for module in modules:
            for node in module.child_resources:
                store_filtered(node, attr_lines.planned.get(node.address, []), planned)
            walk(module.child_modules)

    walk(tree.modules)
    return ResourceAttrLines(planned=planned, drift=drift)


def _build_complex_results(
    tree: PlanTree,
    attr_lines: ResourceAttrLines,
    *,
    terminal_width: int,
    config: ComplexRenderConfig,
    providers: dict[str, str],
    collection_kind: CollectionKindLookup | None,
    lookup: ComputedOnlyLookup,
    show_computed_deltas: bool,
    show_full_config_annex: bool,
    show_create_defaults: bool,
) -> dict[_ComplexKey, ComplexRenderResult]:
    depths = _module_depth_by_address(tree)
    results: dict[_ComplexKey, ComplexRenderResult] = {}
    for node, lines in iter_nodes_with_attr_lines(tree, attr_lines):
        extra_prefix = _tree_extra_prefix(depths.get(node.address, 0))
        provider = providers.get(node.address, "")
        for line in lines:
            if line.value_kind != ValueKind.COMPLEX:
                continue
            key = _ComplexKey(node.address, line.name)
            if key in results:
                continue
            kind = None
            if collection_kind is not None:
                path = tuple(display_path.parse_display_key(line.name))
                kind = collection_kind(provider, node.type, path)
            in_module_tree = extra_prefix > 0
            result = render_complex_value(
                line.old_value,
                line.new_value,
                attr_name=line.name,
                resource_address=node.address,
                indent=MODULE_TREE_ATTR_INDENT if in_module_tree else ATTR_CHANGED_INDENT,
                terminal_width=terminal_width - extra_prefix,
                config=config,
                collection_kind=kind,
                is_sensitive=line.is_sensitive,
                show_full_config_annex=show_full_config_annex,
                show_create_defaults=show_create_defaults,
                change=node.change,
                computed_lookup=lookup,
                provider=provider,
                resource_type=node.type,
                show_computed_deltas=show_computed_deltas,
            )
            filtered = _filter_structural_result(
                result,
                change=node.change,
                lookup=lookup,
                provider=provider,
                resource_type=node.type,
                show_computed_deltas=show_computed_deltas,
            )
            if filtered is not None:
                results[key] = filtered
    return results


def _collect_detail_blocks(results: dict[_ComplexKey, ComplexRenderResult]) -> list[DetailBlock]:
    blocks: list[DetailBlock] = []
    seen: set[_ComplexKey] = set()
    for key, result in results.items():
        if result.detail_block is None or key in seen:
            continue
        blocks.append(result.detail_block)
        seen.add(key)
    return blocks


def _drift_section(
    tree: PlanTree,
    drift_attr_lines: dict[str, list[AttrLine]],
    *,
    complex_results: dict[_ComplexKey, ComplexRenderResult],
    terminal_width: int,
    provider_by_addr: dict[str, str],
    lookup: ComputedOnlyLookup,
    show_computed_drift: bool,
) -> list[Text | str]:
    if not tree.drift:
        return []
    visible = [
        node
        for node in tree.drift
        if show_computed_drift
        or not is_computed_only_drift_resource(
            node,
            drift_attr_lines.get(node.address, []),
            lookup,
            provider=provider_by_addr.get(node.address, ""),
        )
    ]
    if not visible:
        return []
    noun = "resource" if len(visible) == 1 else "resources"
    lines: list[Text | str] = [f"⚠️ Drift: {len(visible)} {noun} changed outside terraform"]
    for node in visible:
        lines.append(_format_drift_resource_header(node))
        if node.action == ResourceAction.DELETE:
            continue
        lines.extend(
            _resource_attr_lines(
                node,
                drift_attr_lines.get(node.address, []),
                complex_results=complex_results,
                terminal_width=terminal_width,
                tree_extra_prefix=0,
            )
        )
    return lines


def _resource_emoji_style(action: ResourceAction) -> tuple[str, str]:
    match action:
        case ResourceAction.CREATE:
            return "🟢", "green"
        case ResourceAction.UPDATE:
            return "🟡", "yellow"
        case ResourceAction.DELETE:
            return "🔴", "red"
        case ResourceAction.REPLACE_DESTROY_FIRST | ResourceAction.REPLACE_CREATE_FIRST:
            return "🟣", "magenta"
        case _:
            return "", ""


def _resource_action_suffix(action: ResourceAction) -> str:
    match action:
        case ResourceAction.DELETE:
            return " (deleted)"
        case ResourceAction.UPDATE:
            return " (updated)"
        case ResourceAction.REPLACE_DESTROY_FIRST | ResourceAction.REPLACE_CREATE_FIRST:
            return " (must replace)"
        case _:
            return ""


def _format_resource_header(node: ResourceNode) -> Text:
    emoji, style = _resource_emoji_style(node.action)
    suffix = _resource_action_suffix(node.action)
    return Text(f"{emoji} {node.address}{suffix}", style=style)


def _format_drift_resource_header(node: ResourceNode) -> Text:
    suffix = _resource_action_suffix(node.action) or " (changed)"
    return Text(f"⚠️ {node.address}{suffix}", style="cyan")


def _format_scalar(value: object) -> str:
    return display_path.inline_json(value)


def _format_attr_value_line(line: AttrLine) -> str:
    if line.is_sensitive:
        return _SENSITIVE
    match line.prefix:
        case None:
            value = line.new_value if line.new_value is not None else line.old_value
            return f"{line.name}: {_format_scalar(value)}"
        case AttrPrefix.ADD:
            return f"{line.name}: {_format_scalar(line.new_value)}"
        case AttrPrefix.REMOVE:
            return f"{line.name}: {_format_scalar(line.old_value)}"
        case AttrPrefix.CHANGE | AttrPrefix.REPLACE:
            if line.old_value is not None and line.new_value is not None:
                return f"{line.name}: {_format_scalar(line.old_value)} -> {_format_scalar(line.new_value)}"
            if line.new_value is not None:
                return f"{line.name}: {_format_scalar(line.new_value)}"
            return f"{line.name}: {_format_scalar(line.old_value)}"


def _style_attr_header(line: AttrLine, *, in_module_tree: bool = False) -> Text:
    pad = " " * _attr_pad_len(line, in_module_tree=in_module_tree)
    text = Text()
    text.append(pad)
    if line.prefix is not None:
        text.append(f"{line.prefix} ")
    text.append(line.name, style="bold" if line.prefix is not None else "")
    text.append(":")
    if line.prefix is None:
        text.stylize("dim")
    return text


def _header_value_fits(
    line: AttrLine,
    value_s: str,
    terminal_width: int,
    *,
    tree_extra_prefix: int,
) -> bool:
    in_module_tree = tree_extra_prefix > 0
    pad_len = _attr_pad_len(line, in_module_tree=in_module_tree)
    prefix = f"{line.prefix} " if line.prefix is not None else ""
    head = f"{' ' * pad_len}{prefix}{line.name}: {value_s}"
    return len(head) <= _attr_line_width(terminal_width, tree_extra_prefix=tree_extra_prefix)


def _style_complex_inline_attr(line: AttrLine, value_s: str, *, in_module_tree: bool = False) -> Text:
    pad = " " * _attr_pad_len(line, in_module_tree=in_module_tree)
    text = Text()
    text.append(pad)
    if line.prefix is not None:
        text.append(f"{line.prefix} ")
        text.append(line.name, style="bold")
        text.append(": ")
        text.append(value_s)
        return text
    text.append(f"{line.name}: ", style="dim")
    text.append(value_s, style="dim")
    return text


def _render_complex_attr(
    line: AttrLine,
    result: ComplexRenderResult,
    terminal_width: int,
    *,
    tree_extra_prefix: int,
) -> list[Text | str]:
    in_module_tree = tree_extra_prefix > 0
    if _is_structural_inline(result.inline_lines):
        pad = " " * _attr_pad_len(line, in_module_tree=in_module_tree)
        return [
            _style_structural_line(f"{pad}{content.strip()}" if content.strip() else content)
            for content in result.inline_lines
        ]
    if (
        result.detail_block is None
        and len(result.inline_lines) == 2
        and result.inline_lines[1].strip().startswith("-> ")
    ):
        value_s = f"{result.inline_lines[0].strip()} {result.inline_lines[1].strip()}"
        if _header_value_fits(line, value_s, terminal_width, tree_extra_prefix=tree_extra_prefix):
            return [_style_complex_inline_attr(line, value_s, in_module_tree=in_module_tree)]
        if split := _complex_inline_old_new_split(
            line,
            result.inline_lines[0].strip(),
            result.inline_lines[1].strip().removeprefix("->").strip(),
            terminal_width,
            tree_extra_prefix=tree_extra_prefix,
        ):
            return cast(list[Text | str], split)
    if result.detail_block is not None or len(result.inline_lines) != 1:
        return [_style_attr_header(line, in_module_tree=in_module_tree), *result.inline_lines]
    value_s = result.inline_lines[0].strip()
    if _header_value_fits(line, value_s, terminal_width, tree_extra_prefix=tree_extra_prefix):
        return [_style_complex_inline_attr(line, value_s, in_module_tree=in_module_tree)]
    return [_style_attr_header(line, in_module_tree=in_module_tree), *result.inline_lines]


def _complex_inline_old_new_split(
    line: AttrLine,
    old_s: str,
    new_s: str,
    terminal_width: int,
    *,
    tree_extra_prefix: int,
) -> list[Text] | None:
    in_module_tree = tree_extra_prefix > 0
    pad = " " * _attr_pad_len(line, in_module_tree=in_module_tree)
    prefix = line.prefix
    if prefix is None:
        return None
    head = f"{pad}{prefix} {line.name}: "
    if len(head) + len(old_s) + 4 + len(new_s) <= _attr_line_width(terminal_width, tree_extra_prefix=tree_extra_prefix):
        return None
    first = Text()
    first.append(pad)
    first.append(f"{prefix} ")
    first.append(line.name, style="bold")
    first.append(": ")
    first.append(old_s, style="dim")
    second = Text()
    second.append(pad)
    second.append("-> ")
    second.append(new_s)
    return [first, second]


def _is_structural_inline(lines: list[str]) -> bool:
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith(("~ ", "+ ", "- ")):
            continue
        key = stripped.split(":", 1)[0]
        if "." in key or "[" in key:
            return True
    return False


def _style_structural_line(line: str) -> Text:
    stripped = line.strip()
    if ": " not in stripped:
        return Text(line)
    prefix_part, value_part = stripped.split(": ", 1)
    space = line[: len(line) - len(line.lstrip())]
    text = Text()
    text.append(space)
    if " -> " in value_part:
        old_s, new_s = value_part.split(" -> ", 1)
        text.append(prefix_part)
        text.append(": ")
        text.append(old_s, style="dim")
        text.append(" -> ")
        text.append(new_s)
        return text
    text.append(prefix_part)
    text.append(": ")
    text.append(value_part)
    return text


def _path_from_structural_line(line: str) -> tuple[str | int, ...]:
    stripped = line.strip()
    key = stripped.split(":", 1)[0]
    marker, _, path_s = key.partition(" ")
    _ = marker
    return tuple(display_path.parse_display_key(path_s))


def _filter_structural_result(
    result: ComplexRenderResult,
    *,
    change: Change,
    lookup: ComputedOnlyLookup,
    provider: str,
    resource_type: str,
    show_computed_deltas: bool,
) -> ComplexRenderResult | None:
    kept: list[str] = []
    for line in result.inline_lines:
        stripped = line.strip()
        if not _is_structural_inline([line]):
            kept.append(line)
            continue
        path = _path_from_structural_line(stripped)
        if is_computed_only_plan_delta(
            path,
            change,
            lookup,
            provider=provider,
            resource_type=resource_type,
        ):
            if show_computed_deltas:
                key = stripped.split(":", 1)[0]
                marker, _, path_s = key.partition(" ")
                kept.append(f"{line[: len(line) - len(stripped)]}{marker} {path_s} (computed, omitted from config)")
            continue
        kept.append(line)
    if not kept:
        return None
    return result.model_copy(update={"inline_lines": kept})


def _style_scalar_attr_line(line: AttrLine, *, in_module_tree: bool = False) -> Text:
    pad = " " * _attr_pad_len(line, in_module_tree=in_module_tree)
    if line.prefix is None:
        return Text(f"{pad}{_format_attr_value_line(line)}", style="dim")
    text = Text()
    text.append(pad)
    text.append(f"{line.prefix} ")
    text.append(line.name, style="bold")
    text.append(": ")
    if line.is_sensitive:
        text.append(_SENSITIVE)
        return text
    match line.prefix:
        case AttrPrefix.ADD:
            text.append(_format_scalar(line.new_value))
        case AttrPrefix.REMOVE:
            text.append(_format_scalar(line.old_value), style="dim")
        case AttrPrefix.CHANGE | AttrPrefix.REPLACE:
            if line.old_value is not None and line.new_value is not None:
                text.append(_format_scalar(line.old_value), style="dim")
                text.append(" -> ")
                text.append(_format_scalar(line.new_value))
            elif line.new_value is not None:
                text.append(_format_scalar(line.new_value))
            else:
                text.append(_format_scalar(line.old_value), style="dim")
    return text


def _attr_pad_len(line: AttrLine, *, in_module_tree: bool = False) -> int:
    if in_module_tree:
        return MODULE_TREE_ATTR_INDENT
    return ATTR_CONTEXT_INDENT if line.prefix is None else ATTR_CHANGED_INDENT


def _attr_line_width(terminal_width: int, *, tree_extra_prefix: int) -> int:
    return max(1, terminal_width - tree_extra_prefix)


def _scalar_value_for_line(line: AttrLine) -> str | None:
    if line.is_sensitive:
        return None
    match line.prefix:
        case None:
            value = line.new_value if line.new_value is not None else line.old_value
        case AttrPrefix.ADD:
            value = line.new_value
        case AttrPrefix.REMOVE:
            value = line.old_value
        case AttrPrefix.CHANGE | AttrPrefix.REPLACE:
            if line.old_value is not None and line.new_value is not None:
                return None
            value = line.new_value if line.new_value is not None else line.old_value
        case _:
            return None
    if value is None:
        return None
    return _format_scalar(value)


def _scalar_old_new_split(line: AttrLine, terminal_width: int, *, tree_extra_prefix: int) -> list[Text] | None:
    if line.is_sensitive:
        return None
    match line.prefix:
        case AttrPrefix.CHANGE | AttrPrefix.REPLACE as prefix:
            pass
        case _:
            return None
    if line.old_value is None or line.new_value is None:
        return None
    in_module_tree = tree_extra_prefix > 0
    pad = " " * _attr_pad_len(line, in_module_tree=in_module_tree)
    old_s = _format_scalar(line.old_value)
    new_s = _format_scalar(line.new_value)
    head = f"{pad}{prefix} {line.name}: "
    if len(head) + len(old_s) + 4 + len(new_s) <= _attr_line_width(terminal_width, tree_extra_prefix=tree_extra_prefix):
        return None
    first = Text()
    first.append(pad)
    first.append(f"{prefix} ")
    first.append(line.name, style="bold")
    first.append(": ")
    first.append(old_s, style="dim")
    second = Text()
    second.append(pad)
    second.append("-> ")
    second.append(new_s)
    return [first, second]


def _scalar_single_value_split(line: AttrLine, terminal_width: int, *, tree_extra_prefix: int) -> list[Text] | None:
    value_s = _scalar_value_for_line(line)
    if value_s is None:
        return None
    in_module_tree = tree_extra_prefix > 0
    pad_len = _attr_pad_len(line, in_module_tree=in_module_tree)
    pad = " " * pad_len
    value_pad = " " * (pad_len + 2)
    available = _attr_line_width(terminal_width, tree_extra_prefix=tree_extra_prefix)
    match line.prefix:
        case None:
            head = f"{pad}{line.name}: "
            first = Text(f"{pad}{line.name}: ", style="dim")
        case AttrPrefix.ADD | AttrPrefix.REMOVE | AttrPrefix.CHANGE | AttrPrefix.REPLACE as prefix:
            head = f"{pad}{prefix} {line.name}: "
            if len(head) + len(value_s) <= available:
                return None
            first = Text()
            first.append(pad)
            first.append(f"{prefix} ")
            first.append(line.name, style="bold")
            first.append(": ")
        case _:
            return None
    if len(head) + len(value_s) <= available:
        return None
    second = Text(value_pad)
    if line.prefix is None:
        second.append(value_s, style="dim")
    elif line.prefix is AttrPrefix.REMOVE:
        second.append(value_s, style="dim")
    else:
        second.append(value_s)
    return [first, second]


def _render_scalar_attr(line: AttrLine, terminal_width: int, *, tree_extra_prefix: int) -> list[Text]:
    if split := _scalar_old_new_split(line, terminal_width, tree_extra_prefix=tree_extra_prefix):
        return split
    if split := _scalar_single_value_split(line, terminal_width, tree_extra_prefix=tree_extra_prefix):
        return split
    return [_style_scalar_attr_line(line, in_module_tree=tree_extra_prefix > 0)]


def _resource_attr_lines(
    node: ResourceNode,
    lines: list[AttrLine],
    *,
    complex_results: dict[_ComplexKey, ComplexRenderResult],
    terminal_width: int,
    tree_extra_prefix: int,
) -> list[Text | str]:
    rendered: list[Text | str] = []
    for line in lines:
        if line.value_kind == ValueKind.COMPLEX:
            key = _ComplexKey(node.address, line.name)
            if key not in complex_results:
                continue
            result = complex_results[key]
            rendered.extend(
                _render_complex_attr(
                    line,
                    result,
                    terminal_width,
                    tree_extra_prefix=tree_extra_prefix,
                )
            )
            continue
        rendered.extend(_render_scalar_attr(line, terminal_width, tree_extra_prefix=tree_extra_prefix))
    return rendered


def _build_module_tree(
    module: ModuleNode,
    attr_lines_by_addr: dict[str, list[AttrLine]],
    *,
    complex_results: dict[_ComplexKey, ComplexRenderResult],
    terminal_width: int,
    module_depths: dict[str, int],
) -> Tree:
    tree = Tree(
        module.name,
        style=_MODULE_TREE_LABEL_STYLE,
        guide_style=_MODULE_TREE_GUIDE_STYLE,
    )
    for node in module.child_resources:
        branch = tree.add(
            _format_resource_header(node),
            guide_style=_MODULE_TREE_GUIDE_STYLE,
        )
        extra = _tree_extra_prefix(module_depths.get(node.address, 0))
        for line in _resource_attr_lines(
            node,
            attr_lines_by_addr.get(node.address, []),
            complex_results=complex_results,
            terminal_width=terminal_width,
            tree_extra_prefix=extra,
        ):
            branch.add(line, guide_style=_MODULE_TREE_GUIDE_STYLE)
    for child in module.child_modules:
        tree.add(
            _build_module_tree(
                child,
                attr_lines_by_addr,
                complex_results=complex_results,
                terminal_width=terminal_width,
                module_depths=module_depths,
            ),
            style=_MODULE_TREE_LABEL_STYLE,
            guide_style=_MODULE_TREE_GUIDE_STYLE,
        )
    return tree


def _output_action_counts(changes: dict[str, OutputChange]) -> tuple[int, int, int]:
    new = changed = deleted = 0
    for change in changes.values():
        key = "+".join(change.actions)
        match key:
            case "create":
                new += 1
            case "update":
                changed += 1
            case "delete":
                deleted += 1
            case _:
                pass
    return new, changed, deleted


def _format_output_section(
    output_changes: dict[str, OutputChange],
    *,
    terminal_width: int,
    show_unknown_outputs: bool,
) -> list[str]:
    entries = _output_entries(output_changes, show_unknown_outputs=show_unknown_outputs)
    if not entries:
        return []
    new, changed, deleted = _output_action_counts({name: change for name, change, _ in entries})
    header_parts: list[str] = []
    if new:
        header_parts.append(f"🟢 {new} new")
    if changed:
        header_parts.append(f"🟡 {changed} changed")
    if deleted:
        header_parts.append(f"🔴 {deleted} deleted")
    lines = [f"📤 Outputs ({', '.join(header_parts)})"]
    for name, change, marker in entries:
        lines.extend(_format_output_entry_lines(name, change, marker, terminal_width=terminal_width))
    return lines


def _output_entries(
    output_changes: dict[str, OutputChange],
    *,
    show_unknown_outputs: bool,
) -> list[tuple[str, OutputChange, str]]:
    entries: list[tuple[str, OutputChange, str]] = []
    for name in sorted(output_changes):
        change = output_changes[name]
        key = "+".join(change.actions)
        match key:
            case "no-op":
                continue
            case "create":
                marker = "+"
            case "update":
                marker = "~"
            case "delete":
                marker = "-"
            case _:
                continue
        if change.after_unknown and not show_unknown_outputs:
            continue
        entries.append((name, change, marker))
    return entries


def _output_value_text(change: OutputChange) -> str:
    if change.before_sensitive or change.after_sensitive:
        return _SENSITIVE
    if change.after_unknown:
        return _KNOWN_AFTER_APPLY
    key = "+".join(change.actions)
    match key:
        case "create":
            return _format_scalar(change.after)
        case "delete":
            return _format_scalar(change.before)
        case "update":
            return f"{_format_scalar(change.before)} -> {_format_scalar(change.after)}"
        case _:
            return ""


def _output_wrap_width(terminal_width: int) -> int:
    return min(terminal_width, OUTPUT_WRAP_WIDTH)


def _format_output_value(value_s: str) -> str:
    if len(value_s) > OUTPUT_MULTILINE_CHARS:
        return _pretty_json_if_structured(value_s) or value_s
    if len(value_s) > OUTPUT_PRETTY_JSON_CHARS:
        pretty = _pretty_json_if_structured(value_s)
        if pretty is not None:
            return pretty
    return value_s


def _pretty_json_if_structured(value_s: str) -> str | None:
    try:
        parsed = json.loads(value_s)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict | list):
        return json.dumps(parsed, sort_keys=True, indent=2)
    return None


def _format_output_entry_lines(name: str, change: OutputChange, marker: str, *, terminal_width: int) -> list[str]:
    pad = " " * OUTPUT_INDENT
    value_pad = " " * (OUTPUT_INDENT + 2)
    value_s = _output_value_text(change)
    if not value_s:
        return [f"{pad}{marker} {name}"]
    head = f"{marker} {name}: "
    value_s = _format_output_value(value_s)
    wrap_width = _output_wrap_width(terminal_width)
    if len(pad) + len(head) + len(value_s) <= wrap_width and "\n" not in value_s:
        return [f"{pad}{head}{value_s}"]
    lines = [f"{pad}{head}"]
    for value_line in value_s.splitlines():
        lines.append(f"{value_pad}{value_line}")
    return lines
