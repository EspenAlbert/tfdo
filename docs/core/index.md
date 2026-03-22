<!-- === DO_NOT_EDIT: pkg-ext header === -->
# core

<!-- === OK_EDIT: pkg-ext header === -->

<!-- === DO_NOT_EDIT: pkg-ext symbols === -->
- [`InitMode`](#initmode_def)
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
- [source](../../tfdo/_internal/core/cmd_apply.py#L11)
> **Since:** 0.1.0

```python
def apply_cmd(*, auto_approve: bool = False, var_file: Path | None = ..., init_mode: InitMode = <InitMode.AUTO: 'auto'>) -> None:
    ...
```

Run terraform apply.

**CLI Options:**

| Flag | Type | Default | Env Var | Description |
|---|---|---|---|---|
| `--auto-approve` | `bool` | `False` | - | Skip interactive approval prompts |
| `--var-file`, `-f` | `Path | None` | *required* | - | Path to a terraform .tfvars file |
| `--init-mode`, `-I` | `InitMode` | `<InitMode.AUTO: 'auto'>` | `TFDO_INIT_MODE` | Init behavior: auto (run init on error related to init), always (run init first), never (skip init) [auto, always, never] |

### Changes

| Version | Change |
|---------|--------|
| 0.1.0 | Made public |
<!-- === OK_EDIT: pkg-ext apply_cmd_def === -->
<!-- === DO_NOT_EDIT: pkg-ext check_cmd_def === -->
<a id="check_cmd_def"></a>

### cli_command: `check_cmd`
- [source](../../tfdo/_internal/core/cmd_check.py#L58)
> **Since:** 0.1.0

```python
def check_cmd(*, fix: bool = False, diff: bool = False, init_mode: InitMode = <InitMode.AUTO: 'auto'>, include: list[str] = [], exclude: list[str] = [], tflint: bool | None = ...) -> None:
    ...
```

Run terraform fmt check + validate (ruff-style).

**CLI Options:**

| Flag | Type | Default | Env Var | Description |
|---|---|---|---|---|
| `--fix` | `bool` | `False` | - | Auto-format instead of checking |
| `--diff` | `bool` | `False` | - | Show what would change |
| `--init-mode`, `-I` | `InitMode` | `<InitMode.AUTO: 'auto'>` | `TFDO_INIT_MODE` | Init behavior: auto (run init on error related to init), always (run init first), never (skip init) [auto, always, never] |
| `--include` | `list[str]` | `[]` | - | Glob patterns: only matching directories are checked |
| `--exclude` | `list[str]` | `[]` | - | Glob patterns: matching directories are skipped |
| `--tflint/--no-tflint` | `bool | None` | *required* | `TFDO_TFLINT` | Run tflint linter alongside fmt+validate |

### Changes

| Version | Change |
|---------|--------|
| 0.1.0 | Made public |
<!-- === OK_EDIT: pkg-ext check_cmd_def === -->
<!-- === DO_NOT_EDIT: pkg-ext destroy_cmd_def === -->
<a id="destroy_cmd_def"></a>

### cli_command: `destroy_cmd`
- [source](../../tfdo/_internal/core/cmd_destroy.py#L11)
> **Since:** 0.1.0

```python
def destroy_cmd(*, auto_approve: bool = False, var_file: Path | None = ..., init_mode: InitMode = <InitMode.AUTO: 'auto'>) -> None:
    ...
```

Run terraform destroy.

**CLI Options:**

| Flag | Type | Default | Env Var | Description |
|---|---|---|---|---|
| `--auto-approve` | `bool` | `False` | - | Skip interactive approval prompts |
| `--var-file`, `-f` | `Path | None` | *required* | - | Path to a terraform .tfvars file |
| `--init-mode`, `-I` | `InitMode` | `<InitMode.AUTO: 'auto'>` | `TFDO_INIT_MODE` | Init behavior: auto (run init on error related to init), always (run init first), never (skip init) [auto, always, never] |

### Changes

| Version | Change |
|---------|--------|
| 0.1.0 | Made public |
<!-- === OK_EDIT: pkg-ext destroy_cmd_def === -->
<!-- === DO_NOT_EDIT: pkg-ext init_cmd_def === -->
<a id="init_cmd_def"></a>

### cli_command: `init_cmd`
- [source](../../tfdo/_internal/core/cmd_init.py#L12)
> **Since:** 0.1.0

```python
def init_cmd(*, extra_args: list[str] | None = ...) -> None:
    ...
```

Run terraform init with retry on transient errors.

**CLI Options:**

| Flag | Type | Default | Description |
|---|---|---|---|
| `extra_args` (arg) | `list[str] | None` | *required* | Extra arguments forwarded to terraform init |

### Changes

| Version | Change |
|---------|--------|
| 0.1.0 | Made public |
<!-- === OK_EDIT: pkg-ext init_cmd_def === -->
<!-- === DO_NOT_EDIT: pkg-ext plan_cmd_def === -->
<a id="plan_cmd_def"></a>

### cli_command: `plan_cmd`
- [source](../../tfdo/_internal/core/cmd_plan.py#L11)
> **Since:** 0.1.0

```python
def plan_cmd(*, out: Path | None = ..., json_output: bool = False, var_file: Path | None = ..., init_mode: InitMode = <InitMode.AUTO: 'auto'>) -> None:
    ...
```

Run terraform plan.

**CLI Options:**

| Flag | Type | Default | Env Var | Description |
|---|---|---|---|---|
| `-o`, `--out` | `Path | None` | *required* | - | Write the plan to a file |
| `--json` | `bool` | `False` | - | Output plan in JSON format |
| `--var-file`, `-f` | `Path | None` | *required* | - | Path to a terraform .tfvars file |
| `--init-mode`, `-I` | `InitMode` | `<InitMode.AUTO: 'auto'>` | `TFDO_INIT_MODE` | Init behavior: auto (run init on error related to init), always (run init first), never (skip init) [auto, always, never] |

### Changes

| Version | Change |
|---------|--------|
| 0.1.0 | Made public |
<!-- === OK_EDIT: pkg-ext plan_cmd_def === -->
<!-- === DO_NOT_EDIT: pkg-ext initmode_def === -->
<a id="initmode_def"></a>

### class: `InitMode`
- [source](../../tfdo/_internal/models.py#L13)
> **Since:** 0.2.0

```python
class InitMode(StrEnum):
    ...
```

### Changes

| Version | Change |
|---------|--------|
| 0.2.0 | Made public |
<!-- === OK_EDIT: pkg-ext initmode_def === -->