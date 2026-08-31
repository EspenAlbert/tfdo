<!-- === DO_NOT_EDIT: pkg-ext header === -->
# new

<!-- === OK_EDIT: pkg-ext header === -->

<!-- === DO_NOT_EDIT: pkg-ext symbols === -->
- [`backend_cmd`](#backend_cmd_def)
- [`run_dir_cmd`](#run_dir_cmd_def)
<!-- === OK_EDIT: pkg-ext symbols === -->

<!-- === DO_NOT_EDIT: pkg-ext symbol_details_header === -->
## Symbol Details
<!-- === OK_EDIT: pkg-ext symbol_details_header === -->

<!-- === DO_NOT_EDIT: pkg-ext backend_cmd_def === -->
<a id="backend_cmd_def"></a>

### cli_command: `backend_cmd`
- [source](../../tfdo/_internal/new/cmd_new.py#L44)
> **Since:** 0.7.0

```python
def backend_cmd(*, bucket: str = ..., region: str = "us-east-1", key: str = "{path}/terraform.tfstate") -> None: ...
```

Write backend.tf to all run-dirs.

**CLI Options:**

| Flag | Type | Default | Description |
|---|---|---|---|
| `--bucket`, `-b` | `str` | *required* | S3 bucket name for Terraform state |
| `--region`, `-r` | `str` | `'us-east-1'` | AWS region |
| `--key` | `str` | `'{path}/terraform.tfstate'` | State key template; {path} is resolved per run-dir |

### Changes

| Version | Change |
|---------|--------|
| 0.7.0 | Made public |
<!-- === OK_EDIT: pkg-ext backend_cmd_def === -->
<!-- === DO_NOT_EDIT: pkg-ext run_dir_cmd_def === -->
<a id="run_dir_cmd_def"></a>

### cli_command: `run_dir_cmd`
- [source](../../tfdo/_internal/new/cmd_new.py#L266)
> **Since:** 0.7.0

```python
def run_dir_cmd() -> None: ...
```

Scaffold a new run-dir with module calls, variables, and outputs.

### Changes

| Version | Change |
|---------|--------|
| 0.7.0 | Made public |
<!-- === OK_EDIT: pkg-ext run_dir_cmd_def === -->