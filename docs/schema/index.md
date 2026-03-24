<!-- === DO_NOT_EDIT: pkg-ext header === -->
# schema

<!-- === OK_EDIT: pkg-ext header === -->

<!-- === DO_NOT_EDIT: pkg-ext symbols === -->
- [`ResourceSchemaChange`](#resourceschemachange_def)
- [`SchemaDiffResult`](#schemadiffresult_def)
- [`schema_diff_cmd`](#schema_diff_cmd_def)
- [`schema_show_cmd`](#schema_show_cmd_def)
<!-- === OK_EDIT: pkg-ext symbols === -->

<!-- === DO_NOT_EDIT: pkg-ext symbol_details_header === -->
## Symbol Details
<!-- === OK_EDIT: pkg-ext symbol_details_header === -->

<!-- === DO_NOT_EDIT: pkg-ext resourceschemachange_def === -->
<a id="resourceschemachange_def"></a>

### class: `ResourceSchemaChange`
- [source](../../tfdo/_internal/schema/diff.py#L38)
> **Since:** unreleased

```python
class ResourceSchemaChange(BaseModel):
    resource_type: str
    path: str
    kind: Literal[added, removed, changed]
    tags: list[str] = ...
```

| Field | Type | Default | Since |
|---|---|---|---|
| resource_type | `str` | - | unreleased |
| path | `str` | - | unreleased |
| kind | `Literal[added, removed, changed]` | - | unreleased |
| tags | `list[str]` | `...` | unreleased |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext resourceschemachange_def === -->
<!-- === DO_NOT_EDIT: pkg-ext schemadiffresult_def === -->
<a id="schemadiffresult_def"></a>

### class: `SchemaDiffResult`
- [source](../../tfdo/_internal/schema/diff.py#L45)
> **Since:** unreleased

```python
class SchemaDiffResult(BaseModel):
    format_version: int = 1
    from_label: str
    to_label: str
    resources_added: list[str] = ...
    resources_removed: list[str] = ...
    changes: list[ResourceSchemaChange] = ...
```

| Field | Type | Default | Since |
|---|---|---|---|
| format_version | `int` | `1` | unreleased |
| from_label | `str` | - | unreleased |
| to_label | `str` | - | unreleased |
| resources_added | `list[str]` | `...` | unreleased |
| resources_removed | `list[str]` | `...` | unreleased |
| changes | `list[ResourceSchemaChange]` | `...` | unreleased |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext schemadiffresult_def === -->
<!-- === DO_NOT_EDIT: pkg-ext schema_diff_cmd_def === -->
<a id="schema_diff_cmd_def"></a>

### cli_command: `schema_diff_cmd`
- [source](../../tfdo/_internal/schema/cmd_schema.py#L67)
> **Since:** unreleased

```python
def schema_diff_cmd(*, provider: str = ..., source: str | None = ..., from_constraint: str | None = ..., to_constraint: str | None = ..., resource: str | None = ..., path_parts: list[str] = [], no_cache: bool = False, as_json: bool = False) -> None:
    ...
```

Compare resource schemas for two version constraints or for registry vs local dev plugin.

Examples:
    tfdo schema diff --provider mongodbatlas --from 1.18.0 --to 1.19.0
    tfdo schema diff --provider aws --source hashicorp/aws --from 5.0.0 --to 5.1.0 --json
    tfdo schema diff --provider mongodbatlas --from 1.18.0
    tfdo schema diff --provider mongodbatlas --from 1.18.0 --to dev
    tfdo schema diff --provider mongodbatlas --to 1.19.0
    tfdo schema diff --provider mongodbatlas --from 1.18.0 --to 1.19.0 --resource mongodbatlas_cluster --path region

**CLI Options:**

| Flag | Type | Default | Description |
|---|---|---|---|
| `--provider` | `str` | *required* | required_providers local name (e.g. mongodbatlas) |
| `--source` | `str | None` | *required* | Registry source namespace/type (optional when tfdo has a built-in default for --provider) |
| `--from` | `str | None` | *required* | Version constraint or literal 'dev'; omit when --to is a version to compare dev plugin to that version |
| `--to` | `str | None` | *required* | Version constraint or literal 'dev'; omit when --from is a version to compare that version to dev plugin |
| `--resource` | `str | None` | *required* | Single resource type to diff (same semantics as schema show) |
| `--path` | `list[str]` | `[]` | Limit attribute/block detail rows to this path or descendants (repeatable); does not filter resource add/remove lists |
| `--no-cache` | `bool` | `False` | Skip schema cache read and write |
| `--json` | `bool` | `False` | Print JSON to stdout |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext schema_diff_cmd_def === -->
<!-- === DO_NOT_EDIT: pkg-ext schema_show_cmd_def === -->
<a id="schema_show_cmd_def"></a>

### cli_command: `schema_show_cmd`
- [source](../../tfdo/_internal/schema/cmd_schema.py#L23)
> **Since:** unreleased

```python
def schema_show_cmd(*, provider: str = ..., source: str | None = ..., version: str = '>= 1.0', resource: str | None = ..., no_cache: bool = False, as_json: bool = False) -> None:
    ...
```

**CLI Options:**

| Flag | Type | Default | Description |
|---|---|---|---|
| `--provider` | `str` | *required* | required_providers local name (e.g. mongodbatlas) |
| `--source` | `str | None` | *required* | Registry source namespace/type (optional when tfdo has a built-in default for --provider) |
| `--version` | `str` | `'>= 1.0'` | required_providers version constraint |
| `--resource` | `str | None` | *required* | Resource type; omit to list types for the provider |
| `--no-cache` | `bool` | `False` | Skip schema cache read and write |
| `--json` | `bool` | `False` | Print JSON to stdout |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext schema_show_cmd_def === -->