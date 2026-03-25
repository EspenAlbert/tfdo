<!-- === DO_NOT_EDIT: pkg-ext header === -->
# inspect

<!-- === OK_EDIT: pkg-ext header === -->

<!-- === DO_NOT_EDIT: pkg-ext symbols === -->
- [`MatchingAttributeDescription`](#matchingattributedescription_def)
- [`MatchingSchemaResource`](#matchingschemaresource_def)
- [`SchemaSearch`](#schemasearch_def)
- [`SchemaSearchRowsBehavior`](#schemasearchrowsbehavior_def)
- [`inspect_api_coverage_cmd`](#inspect_api_coverage_cmd_def)
- [`inspect_hcl_paths_cmd`](#inspect_hcl_paths_cmd_def)
- [`inspect_resource_usage_cmd`](#inspect_resource_usage_cmd_def)
<!-- === OK_EDIT: pkg-ext symbols === -->

<!-- === DO_NOT_EDIT: pkg-ext symbol_details_header === -->
## Symbol Details
<!-- === OK_EDIT: pkg-ext symbol_details_header === -->

<!-- === DO_NOT_EDIT: pkg-ext inspect_hcl_paths_cmd_def === -->
<a id="inspect_hcl_paths_cmd_def"></a>

### cli_command: `inspect_hcl_paths_cmd`
- [source](../../tfdo/_internal/inspect/cmd_inspect.py#L31)
> **Since:** 0.4.0

```python
def inspect_hcl_paths_cmd(*, path: Path = Path('.'), as_json: bool = False, output: Path | None = None) -> None:
    ...
```

**CLI Options:**

| Flag | Type | Default | Description |
|---|---|---|---|
| `--path`, `-p` | `Path` | `Path('.')` | Root directory to scan for Terraform files |
| `--json` | `bool` | `False` | Print JSON to stdout |
| `--output`, `-o` | `Path | None` | `None` | Write JSON here instead of stdout (requires --json) |

### Changes

| Version | Change |
|---------|--------|
| 0.4.0 | Made public |
<!-- === OK_EDIT: pkg-ext inspect_hcl_paths_cmd_def === -->
<!-- === DO_NOT_EDIT: pkg-ext inspect_resource_usage_cmd_def === -->
<a id="inspect_resource_usage_cmd_def"></a>

### cli_command: `inspect_resource_usage_cmd`
- [source](../../tfdo/_internal/inspect/cmd_inspect.py#L55)
> **Since:** 0.4.0

```python
def inspect_resource_usage_cmd(*, path: Path = Path('.'), mode: str = 'all', input_only: bool = True, provider: str = ..., source: str | None = None, version: str = '>= 1.0', no_cache: bool = False, include: list[str] = [], exclude: list[str] = ['.github/*', 'tests/*'], description_keywords: list[str] = [], resource_ignore: list[str] = [], schema_search_path: Path | None = None, output: Path | None = None) -> None:
    ...
```

**CLI Options:**

| Flag | Type | Default | Description |
|---|---|---|---|
| `--path`, `-p` | `Path` | `Path('.')` | Root directory to scan for Terraform files |
| `--mode` | `str` | `'all'` | included \| excluded \| all |
| `--input-only/--no-input-only` | `bool` | `True` | Input paths only in v1 (default: on) |
| `--provider` | `str` | *required* | required_providers local name (e.g. mongodbatlas) |
| `--source` | `str | None` | `None` | Registry source namespace/type (optional when tfdo has a built-in default for --provider) |
| `--version` | `str` | `'>= 1.0'` | required_providers version constraint |
| `--no-cache` | `bool` | `False` | Skip schema cache read and write |
| `--include` | `list[str]` | `[]` | Glob patterns: only matching directories are checked |
| `--exclude` | `list[str]` | `['.github/*', 'tests/*']` | Glob patterns: matching directories are skipped (default .github/* and tests/*; any --exclude replaces defaults) |
| `--description-keyword`, `--keyword` | `list[str]` | `[]` | Search provider schema descriptions for this keyword (repeatable; case-insensitive substring match) |
| `--resource-ignore` | `list[str]` | `[]` | Omit this resource type from description search results (repeatable; only applies with description search) |
| `--schema-search` | `Path | None` | `None` | JSON/YAML file with SchemaSearch fields; --keyword/--resource-ignore override file when those lists are non-empty |
| `--output`, `-o` | `Path | None` | `None` | Write JSON here instead of stdout |

### Changes

| Version | Change |
|---------|--------|
| 0.4.0 | Made public |
<!-- === OK_EDIT: pkg-ext inspect_resource_usage_cmd_def === -->
<!-- === DO_NOT_EDIT: pkg-ext matchingattributedescription_def === -->
<a id="matchingattributedescription_def"></a>

### class: `MatchingAttributeDescription`
- [source](../../tfdo/_internal/inspect/description_search_logic.py#L10)
> **Since:** unreleased

```python
class MatchingAttributeDescription(BaseModel):
    name: str
    keywords: list[str]
    description: str
```

| Field | Type | Default | Since |
|---|---|---|---|
| name | `str` | - | unreleased |
| keywords | `list[str]` | - | unreleased |
| description | `str` | - | unreleased |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext matchingattributedescription_def === -->
<!-- === DO_NOT_EDIT: pkg-ext matchingschemaresource_def === -->
<a id="matchingschemaresource_def"></a>

### class: `MatchingSchemaResource`
- [source](../../tfdo/_internal/inspect/description_search_logic.py#L16)
> **Since:** unreleased

```python
class MatchingSchemaResource(BaseModel):
    name: str
    found_in_rows: bool
    matching_attribute_descriptions: list[MatchingAttributeDescription]
```

| Field | Type | Default | Since |
|---|---|---|---|
| name | `str` | - | unreleased |
| found_in_rows | `bool` | - | unreleased |
| matching_attribute_descriptions | `list[MatchingAttributeDescription]` | - | unreleased |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext matchingschemaresource_def === -->
<!-- === DO_NOT_EDIT: pkg-ext schemasearch_def === -->
<a id="schemasearch_def"></a>

### class: `SchemaSearch`
- [source](../../tfdo/_internal/inspect/resource_usage_logic.py#L52)
> **Since:** unreleased

```python
class SchemaSearch(BaseModel):
    description_keywords: list[str] = ...
    resource_ignore: list[str] = ...
    include_data_sources: bool = False
    rows_behavior: SchemaSearchRowsBehavior = <SchemaSearchRowsBehavior.DEFAULT: 'default'>
```

| Field | Type | Default | Since |
|---|---|---|---|
| description_keywords | `list[str]` | `...` | unreleased |
| resource_ignore | `list[str]` | `...` | unreleased |
| include_data_sources | `bool` | `False` | unreleased |
| rows_behavior | `SchemaSearchRowsBehavior` | `<SchemaSearchRowsBehavior.DEFAULT: 'default'>` | unreleased |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext schemasearch_def === -->
<!-- === DO_NOT_EDIT: pkg-ext schemasearchrowsbehavior_def === -->
<a id="schemasearchrowsbehavior_def"></a>

### class: `SchemaSearchRowsBehavior`
- [source](../../tfdo/_internal/inspect/resource_usage_logic.py#L46)
> **Since:** unreleased

```python
class SchemaSearchRowsBehavior(StrEnum):
    ...
```

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext schemasearchrowsbehavior_def === -->
<!-- === DO_NOT_EDIT: pkg-ext inspect_api_coverage_cmd_def === -->
<a id="inspect_api_coverage_cmd_def"></a>

### cli_command: `inspect_api_coverage_cmd`
- [source](../../tfdo/_internal/inspect/cmd_inspect.py#L137)
> **Since:** unreleased

```python
def inspect_api_coverage_cmd(*, api_attributes_file: Path = ..., provider: str = 'mongodbatlas', source: str | None = None, version: str = '>= 1.0', no_cache: bool = False, resource: list[str] = [], include_computed: bool = True, coverage_config_path: Path | None = None, output: Path | None = None) -> None:
    ...
```

**CLI Options:**

| Flag | Type | Default | Description |
|---|---|---|---|
| `--api-attributes-file`, `-a` | `Path` | *required* | Path to api-attributes.json |
| `--provider` | `str` | `'mongodbatlas'` | Provider local name |
| `--source` | `str | None` | `None` | Registry source namespace/type |
| `--version` | `str` | `'>= 1.0'` | required_providers version constraint |
| `--no-cache` | `bool` | `False` | Skip schema cache |
| `--resource` | `list[str]` | `[]` | Filter to specific resource types (repeatable) |
| `--include-computed/--no-include-computed` | `bool` | `True` | Include computed attrs |
| `--coverage-config`, `-c` | `Path | None` | `None` | YAML config with resource mapping and known gaps |
| `--output`, `-o` | `Path | None` | `None` | Write JSON here instead of stdout |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext inspect_api_coverage_cmd_def === -->
