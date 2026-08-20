<!-- === DO_NOT_EDIT: pkg-ext header === -->
# sync

<!-- === OK_EDIT: pkg-ext header === -->

<!-- === DO_NOT_EDIT: pkg-ext symbols === -->
- [`github_cmd`](#github_cmd_def)
- [`justfile_cmd`](#justfile_cmd_def)
<!-- === OK_EDIT: pkg-ext symbols === -->

<!-- === DO_NOT_EDIT: pkg-ext symbol_details_header === -->
## Symbol Details
<!-- === OK_EDIT: pkg-ext symbol_details_header === -->

<!-- === DO_NOT_EDIT: pkg-ext github_cmd_def === -->
<a id="github_cmd_def"></a>

### cli_command: `github_cmd`
- [source](../../tfdo/_internal/sync/cmd_sync.py#L86)
> **Since:** 0.7.0

```python
def github_cmd(
    *, dry_run: bool = False, replace_existing_github_secrets: bool = False, env: str | None = None, oidc: bool = False
) -> None: ...
```

Scaffold GitHub Actions workflows and sync secrets/variables per environment.

**CLI Options:**

| Flag | Type | Default | Description |
|---|---|---|---|
| `--dry-run/--no-dry-run` | `bool` | `False` | Log actions without writing files or calling gh |
| `--replace` | `bool` | `False` | Overwrite Actions environment secrets that already exist on GitHub (default only creates missing ones) |
| `--env` | `str | None` | `None` | Sync only this environment |
| `--oidc/--no-oidc` | `bool` | `False` | Provision GitHub OIDC provider and per-env IAM roles for S3 backend |

### Changes

| Version | Change |
|---------|--------|
| 0.7.0 | Made public |
<!-- === OK_EDIT: pkg-ext github_cmd_def === -->
<!-- === DO_NOT_EDIT: pkg-ext justfile_cmd_def === -->
<a id="justfile_cmd_def"></a>

### cli_command: `justfile_cmd`
- [source](../../tfdo/_internal/sync/cmd_sync.py#L29)
> **Since:** 0.7.0

```python
def justfile_cmd() -> None: ...
```

Generate repo-level justfile with per-env (and per-run-dir) Terraform targets.

### Changes

| Version | Change |
|---------|--------|
| 0.7.0 | Made public |
<!-- === OK_EDIT: pkg-ext justfile_cmd_def === -->