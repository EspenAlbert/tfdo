<!-- === DO_NOT_EDIT: pkg-ext header === -->
# inspect

<!-- === OK_EDIT: pkg-ext header === -->

<!-- === DO_NOT_EDIT: pkg-ext symbols === -->
- [`inspect_hcl_paths_cmd`](#inspect_hcl_paths_cmd_def)
- [`inspect_resource_usage_cmd`](#inspect_resource_usage_cmd_def)
<!-- === OK_EDIT: pkg-ext symbols === -->

<!-- === DO_NOT_EDIT: pkg-ext symbol_details_header === -->
## Symbol Details
<!-- === OK_EDIT: pkg-ext symbol_details_header === -->

<!-- === DO_NOT_EDIT: pkg-ext inspect_hcl_paths_cmd_def === -->
<a id="inspect_hcl_paths_cmd_def"></a>

### cli_command: `inspect_hcl_paths_cmd`
- [source](../../tfdo/_internal/inspect/cmd_inspect.py#L19)
> **Since:** 0.4.0

```python
def inspect_hcl_paths_cmd(*, path: Path = Path('<outside package>'), as_json: bool = False) -> None:
    ...
```

**CLI Options:**

| Flag | Type | Default | Description |
|---|---|---|---|
| `--path`, `-p` | `Path` | `Path('<outside package>')` | Root directory to scan for Terraform files |
| `--json` | `bool` | `False` | Print JSON to stdout |

### Changes

| Version | Change |
|---------|--------|
| 0.4.0 | Made public |
<!-- === OK_EDIT: pkg-ext inspect_hcl_paths_cmd_def === -->
<!-- === DO_NOT_EDIT: pkg-ext inspect_resource_usage_cmd_def === -->
<a id="inspect_resource_usage_cmd_def"></a>

### cli_command: `inspect_resource_usage_cmd`
- [source](../../tfdo/_internal/inspect/cmd_inspect.py#L36)
> **Since:** 0.4.0

```python
def inspect_resource_usage_cmd(*, path: Path = Path('<outside package>'), mode: str = 'all', input_only: bool = True, provider: str = ..., source: str | None = None, version: str = '>= 1.0', no_cache: bool = False, include: list[str] = [], exclude: list[str] = ['.github/*', 'tests/*']) -> None:
    ...
```

**CLI Options:**

| Flag | Type | Default | Description |
|---|---|---|---|
| `--path`, `-p` | `Path` | `Path('<outside package>')` | Root directory to scan for Terraform files |
| `--mode` | `str` | `'all'` | included \| excluded \| all |
| `--input-only/--no-input-only` | `bool` | `True` | Input paths only in v1 (default: on) |
| `--provider` | `str` | *required* | required_providers local name (e.g. mongodbatlas) |
| `--source` | `str | None` | `None` | Registry source namespace/type (optional when tfdo has a built-in default for --provider) |
| `--version` | `str` | `'>= 1.0'` | required_providers version constraint |
| `--no-cache` | `bool` | `False` | Skip schema cache read and write |
| `--include` | `list[str]` | `[]` | Glob patterns: only matching directories are checked |
| `--exclude` | `list[str]` | `['.github/*', 'tests/*']` | Glob patterns: matching directories are skipped (default .github/* and tests/*; any --exclude replaces defaults) |

### Changes

| Version | Change |
|---------|--------|
| 0.4.0 | Made public |
<!-- === OK_EDIT: pkg-ext inspect_resource_usage_cmd_def === -->