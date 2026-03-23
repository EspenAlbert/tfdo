from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Final, Literal, Self

from ask_shell import console
from pydantic import BaseModel, Field, model_validator
from rich.table import Table

from tfdo._internal.schema import inspect_logic as schema_inspect_logic
from tfdo._internal.schema import terraform_cli_config as tf_cli
from tfdo._internal.schema.models import ResourceSchema, SchemaAttribute, SchemaBlock, SchemaBlockType
from tfdo._internal.settings import TfDoSettings

DEV_SIDE_TOKEN: Final[str] = "dev"
DEV_BOOTSTRAP_VERSION: Final[str] = ">= 1.0"


class SchemaDiffSide(BaseModel):
    version_constraint: str
    use_dev_overrides: bool
    display: str


class SchemaDiffInput(BaseModel):
    settings: TfDoSettings
    provider: str
    source: str | None = None
    left: SchemaDiffSide
    right: SchemaDiffSide
    no_cache: bool = False
    attribute_paths: list[str] | None = None
    resource: str | None = None


class ResourceSchemaChange(BaseModel):
    resource_type: str
    path: str
    kind: Literal["added", "removed", "changed"]
    tags: list[str] = Field(default_factory=list)


class SchemaDiffResult(BaseModel):
    format_version: int = 1
    from_label: str
    to_label: str
    resources_added: list[str] = Field(default_factory=list)
    resources_removed: list[str] = Field(default_factory=list)
    changes: list[ResourceSchemaChange] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sort(self) -> Self:
        self.resources_added.sort()
        self.resources_removed.sort()
        self.changes.sort(key=lambda c: (c.resource_type, c.path, c.kind))
        return self

    def to_json(self) -> str:
        return f"{json.dumps(self.model_dump(mode='json'), indent=2, sort_keys=True)}\n"


def _norm_side_arg(s: str | None) -> str | None:
    if s is None:
        return None
    t = s.strip()
    return t or None


def resolve_schema_diff_sides(from_raw: str | None, to_raw: str | None) -> tuple[SchemaDiffSide, SchemaDiffSide]:
    f = _norm_side_arg(from_raw)
    t = _norm_side_arg(to_raw)

    def is_dev(s: str) -> bool:
        return s == DEV_SIDE_TOKEN

    if f is None and t is None:
        raise ValueError("pass --from and/or --to (one may be omitted when inferring dev vs registry)")

    if f is None:
        if t is None or is_dev(t):
            raise ValueError("omit --from only when --to is a version constraint")
        return (
            SchemaDiffSide(
                version_constraint=DEV_BOOTSTRAP_VERSION,
                use_dev_overrides=True,
                display=DEV_SIDE_TOKEN,
            ),
            SchemaDiffSide(version_constraint=t, use_dev_overrides=False, display=t),
        )

    if t is None:
        if is_dev(f):
            raise ValueError("omit --to only when --from is a version constraint")
        return (
            SchemaDiffSide(version_constraint=f, use_dev_overrides=False, display=f),
            SchemaDiffSide(
                version_constraint=DEV_BOOTSTRAP_VERSION,
                use_dev_overrides=True,
                display=DEV_SIDE_TOKEN,
            ),
        )

    if is_dev(f) and is_dev(t):
        raise ValueError("cannot compare dev to dev")

    if is_dev(f):
        return (
            SchemaDiffSide(
                version_constraint=DEV_BOOTSTRAP_VERSION,
                use_dev_overrides=True,
                display=DEV_SIDE_TOKEN,
            ),
            SchemaDiffSide(version_constraint=t, use_dev_overrides=False, display=t),
        )
    if is_dev(t):
        return (
            SchemaDiffSide(version_constraint=f, use_dev_overrides=False, display=f),
            SchemaDiffSide(
                version_constraint=DEV_BOOTSTRAP_VERSION,
                use_dev_overrides=True,
                display=DEV_SIDE_TOKEN,
            ),
        )
    return (
        SchemaDiffSide(version_constraint=f, use_dev_overrides=False, display=f),
        SchemaDiffSide(version_constraint=t, use_dev_overrides=False, display=t),
    )


def ensure_dev_overrides_ready(*, registry_source: str) -> None:
    raw = os.environ.get(tf_cli.TF_CLI_CONFIG_FILE_ENV, "").strip()
    if raw:
        cfg = Path(raw).expanduser()
        if cfg.is_file():
            overrides = tf_cli.parse_dev_overrides(cfg)
            if tf_cli.lookup_plugin_dir(overrides, registry_source=registry_source) is None:
                raise ValueError(f"no dev_overrides entry for registry source {registry_source!r} in {raw}")
            return
        raise ValueError(f"TF_CLI_CONFIG_FILE is not a file: {raw}")
    raise ValueError("dev side requires TF_CLI_CONFIG_FILE in the environment")


def join_path(prefix: str, name: str) -> str:
    return name if not prefix else f"{prefix}.{name}"


def _attr_tags(old: SchemaAttribute, new: SchemaAttribute) -> list[str]:
    tags: list[str] = []
    od = old.model_dump(mode="json", exclude_none=True)
    nd = new.model_dump(mode="json", exclude_none=True)
    if od == nd:
        return []
    for k in ("type", "element_type", "nested_type"):
        if od.get(k) != nd.get(k):
            tags.append("type")
            break
    req_o, req_n = old.required is True, new.required is True
    if req_o != req_n:
        tags.append("required_to_optional" if req_o and not req_n else "optional_to_required")
    elif (old.optional, old.computed, old.required) != (new.optional, new.computed, new.required):
        tags.append("optionality")
    if not tags:
        tags.append("metadata")
    return tags


def _block_type_shell(bt: SchemaBlockType) -> dict[str, Any]:
    d = bt.model_dump(mode="json", exclude_none=True)
    d.pop("block", None)
    return d


def diff_blocks(
    left: SchemaBlock,
    right: SchemaBlock,
    resource_type: str,
    prefix: str,
    out: list[ResourceSchemaChange],
) -> None:
    la = left.attributes or {}
    ra = right.attributes or {}
    for name in sorted(set(la) | set(ra)):
        path = join_path(prefix, name)
        if name not in ra:
            out.append(ResourceSchemaChange(resource_type=resource_type, path=path, kind="removed"))
            continue
        if name not in la:
            out.append(ResourceSchemaChange(resource_type=resource_type, path=path, kind="added"))
            continue
        a_old, a_new = la[name], ra[name]
        od = a_old.model_dump(mode="json", exclude_none=True)
        nd = a_new.model_dump(mode="json", exclude_none=True)
        if od != nd:
            out.append(
                ResourceSchemaChange(
                    resource_type=resource_type,
                    path=path,
                    kind="changed",
                    tags=_attr_tags(a_old, a_new),
                )
            )

    lb = left.block_types or {}
    rb = right.block_types or {}
    for name in sorted(set(lb) | set(rb)):
        path = join_path(prefix, name)
        if name not in rb:
            out.append(
                ResourceSchemaChange(resource_type=resource_type, path=path, kind="removed", tags=["block_type"])
            )
            continue
        if name not in lb:
            out.append(ResourceSchemaChange(resource_type=resource_type, path=path, kind="added", tags=["block_type"]))
            continue
        bt_o, bt_n = lb[name], rb[name]
        if _block_type_shell(bt_o) != _block_type_shell(bt_n):
            out.append(
                ResourceSchemaChange(
                    resource_type=resource_type,
                    path=path,
                    kind="changed",
                    tags=["block_type"],
                )
            )
        diff_blocks(bt_o.block, bt_n.block, resource_type, path, out)


def _format_side_label(display: str, resolved: str | None, use_dev: bool) -> str:
    label = "dev (TF_CLI_CONFIG_FILE)" if use_dev and display == DEV_SIDE_TOKEN else display
    if resolved:
        return f"{label} (lock {resolved})"
    return label


def _matches_path_filter(change_path: str, filters: list[str] | None) -> bool:
    if not filters:
        return True
    return any(change_path == p or change_path.startswith(f"{p}.") for p in filters)


def compute_schema_diff(
    *,
    left_map: dict[str, ResourceSchema],
    right_map: dict[str, ResourceSchema],
    attribute_paths: list[str] | None,
    resource_filter: str | None,
) -> tuple[list[str], list[str], list[ResourceSchemaChange]]:
    if resource_filter:
        left_map = {k: v for k, v in left_map.items() if k == resource_filter}
        right_map = {k: v for k, v in right_map.items() if k == resource_filter}
        if not left_map and not right_map:
            raise ValueError(f"Resource {resource_filter!r} not found on either side")

    added = sorted(set(right_map) - set(left_map))
    removed = sorted(set(left_map) - set(right_map))
    changes: list[ResourceSchemaChange] = []
    for rt in sorted(set(left_map) & set(right_map)):
        diff_blocks(left_map[rt].block, right_map[rt].block, rt, "", changes)

    filtered = [c for c in changes if _matches_path_filter(c.path, attribute_paths)]
    return added, removed, filtered


def schema_diff(inp: SchemaDiffInput) -> SchemaDiffResult:
    source = schema_inspect_logic.resolve_registry_source(provider=inp.provider, source=inp.source)
    if inp.left.use_dev_overrides:
        ensure_dev_overrides_ready(registry_source=source)
    if inp.right.use_dev_overrides:
        ensure_dev_overrides_ready(registry_source=source)

    left_map, left_v = schema_inspect_logic.load_provider_resource_schemas_with_meta(
        settings=inp.settings,
        provider=inp.provider,
        source=inp.source,
        version=inp.left.version_constraint,
        no_cache=inp.no_cache,
        use_dev_overrides=inp.left.use_dev_overrides,
    )
    right_map, right_v = schema_inspect_logic.load_provider_resource_schemas_with_meta(
        settings=inp.settings,
        provider=inp.provider,
        source=inp.source,
        version=inp.right.version_constraint,
        no_cache=inp.no_cache,
        use_dev_overrides=inp.right.use_dev_overrides,
    )

    from_label = _format_side_label(inp.left.display, left_v, inp.left.use_dev_overrides)
    to_label = _format_side_label(inp.right.display, right_v, inp.right.use_dev_overrides)

    added, removed, chg = compute_schema_diff(
        left_map=left_map,
        right_map=right_map,
        attribute_paths=inp.attribute_paths,
        resource_filter=inp.resource,
    )

    return SchemaDiffResult(
        from_label=from_label,
        to_label=to_label,
        resources_added=added,
        resources_removed=removed,
        changes=chg,
    )


def render_schema_diff_rich(result: SchemaDiffResult) -> None:
    console.print_to_live(f"[bold]Schema diff[/bold]\n{result.from_label} -> {result.to_label}")
    if result.resources_added:
        console.print_to_live("[green]Resources added[/green]: " + ", ".join(result.resources_added))
    if result.resources_removed:
        console.print_to_live("[red]Resources removed[/red]: " + ", ".join(result.resources_removed))
    if not result.changes and not result.resources_added and not result.resources_removed:
        console.print_to_live("No differences.")
        return
    if not result.changes:
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("Resource")
    table.add_column("Path")
    table.add_column("Kind")
    table.add_column("Tags")
    for c in result.changes:
        table.add_row(c.resource_type, c.path, c.kind, ", ".join(c.tags))
    console.print_to_live(table)
