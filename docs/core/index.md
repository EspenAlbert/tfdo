<!-- === DO_NOT_EDIT: pkg-ext header === -->
# core

<!-- === OK_EDIT: pkg-ext header === -->

<!-- === DO_NOT_EDIT: pkg-ext symbols === -->
- [`apply_cmd`](#apply_cmd_def)
- [`check_cmd`](#check_cmd_def)
- [`destroy_cmd`](#destroy_cmd_def)
- [`init_cmd`](#init_cmd_def)
- [`plan_cmd`](#plan_cmd_def)
<!-- === OK_EDIT: pkg-ext symbols === -->

<!-- === DO_NOT_EDIT: pkg-ext symbol_details_header === -->
## Symbol Details
<!-- === OK_EDIT: pkg-ext symbol_details_header === -->

<!-- === DO_NOT_EDIT: pkg-ext apply_cmd_def === -->
<a id="apply_cmd_def"></a>

### cli_command: `apply_cmd`
- [source](../../tfdo/_internal/core/cmd_apply.py#L13)
> **Since:** unreleased

```python
def apply_cmd(*, auto_approve: bool = False, var_file: Path | None = ..., init_first: bool = False) -> None:
    ...
```

Run terraform apply.

**CLI Options:**

| Flag | Type | Default | Description |
|---|---|---|---|
| `--auto-approve` | `bool` | `False` | Skip interactive approval prompts |
| `--var-file`, `-f` | `Path | None` | *required* | Path to a terraform .tfvars file |
| `--init` | `bool` | `False` | Run terraform init before the command |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext apply_cmd_def === -->
<!-- === DO_NOT_EDIT: pkg-ext check_cmd_def === -->
<a id="check_cmd_def"></a>

### cli_command: `check_cmd`
- [source](../../tfdo/_internal/core/cmd_check.py#L12)
> **Since:** unreleased

```python
def check_cmd(*, fix: bool = False, diff: bool = False, init_first: bool = False) -> None:
    ...
```

Run terraform fmt check + validate (ruff-style).

**CLI Options:**

| Flag | Type | Default | Description |
|---|---|---|---|
| `--fix` | `bool` | `False` | Auto-format instead of checking |
| `--diff` | `bool` | `False` | Show what would change |
| `--init` | `bool` | `False` | Run terraform init before the command |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext check_cmd_def === -->
<!-- === DO_NOT_EDIT: pkg-ext destroy_cmd_def === -->
<a id="destroy_cmd_def"></a>

### cli_command: `destroy_cmd`
- [source](../../tfdo/_internal/core/cmd_destroy.py#L13)
> **Since:** unreleased

```python
def destroy_cmd(*, auto_approve: bool = False, var_file: Path | None = ..., init_first: bool = False) -> None:
    ...
```

Run terraform destroy.

**CLI Options:**

| Flag | Type | Default | Description |
|---|---|---|---|
| `--auto-approve` | `bool` | `False` | Skip interactive approval prompts |
| `--var-file`, `-f` | `Path | None` | *required* | Path to a terraform .tfvars file |
| `--init` | `bool` | `False` | Run terraform init before the command |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext destroy_cmd_def === -->
<!-- === DO_NOT_EDIT: pkg-ext init_cmd_def === -->
<a id="init_cmd_def"></a>

### cli_command: `init_cmd`
- [source](../../tfdo/_internal/core/cmd_init.py#L11)
> **Since:** unreleased

```python
def init_cmd(*, extra_args: list[str] = ...) -> None:
    ...
```

Run terraform init with retry on transient errors.

**CLI Options:**

| Flag | Type | Default | Description |
|---|---|---|---|
| `extra_args` (arg) | `list[str]` | *required* | Extra arguments forwarded to terraform init |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext init_cmd_def === -->
<!-- === DO_NOT_EDIT: pkg-ext plan_cmd_def === -->
<a id="plan_cmd_def"></a>

### cli_command: `plan_cmd`
- [source](../../tfdo/_internal/core/cmd_plan.py#L13)
> **Since:** unreleased

```python
def plan_cmd(*, out: Path | None = ..., json_output: bool = False, var_file: Path | None = ..., init_first: bool = False) -> None:
    ...
```

Run terraform plan.

**CLI Options:**

| Flag | Type | Default | Description |
|---|---|---|---|
| `-o`, `--out` | `Path | None` | *required* | Write the plan to a file |
| `--json` | `bool` | `False` | Output plan in JSON format |
| `--var-file`, `-f` | `Path | None` | *required* | Path to a terraform .tfvars file |
| `--init` | `bool` | `False` | Run terraform init before the command |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext plan_cmd_def === -->