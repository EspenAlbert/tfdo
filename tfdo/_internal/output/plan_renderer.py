from __future__ import annotations

import json
from typing import NamedTuple

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
from tfdo._internal.output.models import OutputChange, ResourceAction
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
    complex_config: ComplexRenderConfig | None = None,
    show_unknown_outputs: bool = True,
) -> None:
    config = complex_config or ComplexRenderConfig()
    complex_results = _build_complex_results(
        tree,
        attr_lines,
        terminal_width=terminal_width,
        config=config,
        providers=provider_by_addr or {},
        collection_kind=collection_kind,
    )
    state = _PrintState()
    _print_detail_blocks(state, _collect_detail_blocks(complex_results))
    _print_drift(state, tree, attr_lines.drift, complex_results, terminal_width)

    header = _plan_header_line(tree, _action_counts(tree))
    state.emit(header.line)
    if header.subtitle:
        state.emit(header.subtitle, style="dim")
    if not header.render_body:
        return

    state.blank()
    _print_destroy_warning(state, tree)
    _print_resources(state, tree, attr_lines.planned, complex_results, terminal_width)
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
) -> None:
    drift_lines = _drift_section(
        tree,
        drift_attr_lines,
        complex_results=complex_results,
        terminal_width=terminal_width,
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


def _build_complex_results(
    tree: PlanTree,
    attr_lines: ResourceAttrLines,
    *,
    terminal_width: int,
    config: ComplexRenderConfig,
    providers: dict[str, str],
    collection_kind: CollectionKindLookup | None,
) -> dict[_ComplexKey, ComplexRenderResult]:
    depths = _module_depth_by_address(tree)
    results: dict[_ComplexKey, ComplexRenderResult] = {}
    for node, lines in iter_nodes_with_attr_lines(tree, attr_lines):
        extra_prefix = _tree_extra_prefix(depths.get(node.address, 0))
        for line in lines:
            if line.value_kind != ValueKind.COMPLEX:
                continue
            key = _ComplexKey(node.address, line.name)
            if key in results:
                continue
            kind = None
            if collection_kind is not None:
                path = tuple(display_path.parse_display_key(line.name))
                kind = collection_kind(providers.get(node.address, ""), node.type, path)
            results[key] = render_complex_value(
                line.old_value,
                line.new_value,
                attr_name=line.name,
                resource_address=node.address,
                indent=ATTR_CHANGED_INDENT,
                terminal_width=terminal_width - extra_prefix,
                config=config,
                collection_kind=kind,
                is_sensitive=line.is_sensitive,
            )
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
) -> list[Text | str]:
    if not tree.drift:
        return []
    noun = "resource" if len(tree.drift) == 1 else "resources"
    lines: list[Text | str] = [f"⚠️ Drift: {len(tree.drift)} {noun} changed outside terraform"]
    for node in tree.drift:
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


def _style_attr_header(line: AttrLine) -> Text:
    pad = " " * _attr_pad_len(line)
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
    pad_len = _attr_pad_len(line)
    prefix = f"{line.prefix} " if line.prefix is not None else ""
    head = f"{' ' * pad_len}{prefix}{line.name}: {value_s}"
    return len(head) <= _attr_line_width(terminal_width, tree_extra_prefix=tree_extra_prefix)


def _style_complex_inline_attr(line: AttrLine, value_s: str) -> Text:
    pad = " " * _attr_pad_len(line)
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
    if result.detail_block is not None or len(result.inline_lines) != 1:
        return [_style_attr_header(line), *result.inline_lines]
    value_s = result.inline_lines[0].strip()
    if _header_value_fits(line, value_s, terminal_width, tree_extra_prefix=tree_extra_prefix):
        return [_style_complex_inline_attr(line, value_s)]
    return [_style_attr_header(line), *result.inline_lines]


def _style_scalar_attr_line(line: AttrLine) -> Text:
    if line.prefix is None:
        return Text(f"{' ' * ATTR_CONTEXT_INDENT}{_format_attr_value_line(line)}", style="dim")
    pad = " " * ATTR_CHANGED_INDENT
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


def _attr_pad_len(line: AttrLine) -> int:
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
    pad = " " * _attr_pad_len(line)
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
    pad_len = _attr_pad_len(line)
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
    return [_style_scalar_attr_line(line)]


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
            result = complex_results[_ComplexKey(node.address, line.name)]
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
