<!-- === DO_NOT_EDIT: pkg-ext header === -->
# copy

<!-- === OK_EDIT: pkg-ext header === -->

<!-- === DO_NOT_EDIT: pkg-ext symbols === -->
- [`env_cmd`](#env_cmd_def)
<!-- === OK_EDIT: pkg-ext symbols === -->

<!-- === DO_NOT_EDIT: pkg-ext symbol_details_header === -->
## Symbol Details
<!-- === OK_EDIT: pkg-ext symbol_details_header === -->

<!-- === DO_NOT_EDIT: pkg-ext env_cmd_def === -->
<a id="env_cmd_def"></a>

### cli_command: `env_cmd`
- [source](../../tfdo/_internal/copy/cmd_copy.py#L99)
> **Since:** 0.7.0

```python
def env_cmd(*, src: str = ..., dst: str = ...) -> None: ...
```

Copy a tfdo-managed environment.

**CLI Options:**

| Flag | Type | Default | Description |
|---|---|---|---|
| `--from` | `str` | *required* | Source env name |
| `--to` | `str` | *required* | Destination env name |

### Changes

| Version | Change |
|---------|--------|
| 0.7.0 | Made public |
<!-- === OK_EDIT: pkg-ext env_cmd_def === -->