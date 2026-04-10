<!-- === DO_NOT_EDIT: pkg-ext header === -->
# run

<!-- === OK_EDIT: pkg-ext header === -->

<!-- === DO_NOT_EDIT: pkg-ext symbols === -->
- [`run_apply_cmd`](#run_apply_cmd_def)
- [`run_callback`](#run_callback_def)
- [`run_destroy_cmd`](#run_destroy_cmd_def)
- [`run_init_cmd`](#run_init_cmd_def)
- [`run_plan_cmd`](#run_plan_cmd_def)
<!-- === OK_EDIT: pkg-ext symbols === -->

<!-- === DO_NOT_EDIT: pkg-ext symbol_details_header === -->
## Symbol Details
<!-- === OK_EDIT: pkg-ext symbol_details_header === -->

<!-- === DO_NOT_EDIT: pkg-ext run_apply_cmd_def === -->
<a id="run_apply_cmd_def"></a>

### cli_command: `run_apply_cmd`
- [source](../../tfdo/_internal/run/cmd_run.py#L105)
> **Since:** unreleased

```python
def run_apply_cmd(*, auto_approve: bool = False, var_file: Path | None = None, init_mode: InitMode = <InitMode.AUTO: 'auto'>) -> None:
    ...
```

Run apply across multiple run directories.

**CLI Options:**

| Flag | Type | Default | Env Var | Description |
|---|---|---|---|---|
| `--auto-approve` | `bool` | `False` | - | Skip interactive approval prompts |
| `--var-file`, `-f` | `Path | None` | `None` | - | Path to a terraform .tfvars file |
| `--init-mode`, `-I` | `InitMode` | `<InitMode.AUTO: 'auto'>` | `TFDO_INIT_MODE` | Init behavior: auto (run init on error related to init), always (run init first), never (skip init) [auto, always, never] |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext run_apply_cmd_def === -->
<!-- === DO_NOT_EDIT: pkg-ext run_callback_def === -->
<a id="run_callback_def"></a>

### cli_command: `run_callback`
- [source](../../tfdo/_internal/run/cmd_run.py#L44)
> **Since:** unreleased

```python
def run_callback(*, env: str | None = None, app_name: str | None = None, tags: list[str] = [], parallel: int = 10, on_failure: FailureMode = <FailureMode.STOP: 'stop'>, dry_run: bool = False) -> None:
    ...
```

**CLI Options:**

| Flag | Type | Default | Description |
|---|---|---|---|
| `--env` | `str | None` | `None` | Filter run directories by {env} selector from discovery pattern |
| `--app` | `str | None` | `None` | Filter run directories by {app} selector from discovery pattern |
| `--tags` | `list[str]` | `[]` | Tag filter as key=value, repeatable with AND logic (e.g. --tags env=dev --tags team=infra) |
| `--parallel` | `int` | `10` | Max concurrent run directory executions per wave |
| `--on-failure` | `FailureMode` | `<FailureMode.STOP: 'stop'>` | Failure behavior: stop aborts remaining directories, continue runs all [stop, continue] |
| `--dry-run` | `bool` | `False` | Show execution plan (waves and run directories) without running terraform |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext run_callback_def === -->
<!-- === DO_NOT_EDIT: pkg-ext run_destroy_cmd_def === -->
<a id="run_destroy_cmd_def"></a>

### cli_command: `run_destroy_cmd`
- [source](../../tfdo/_internal/run/cmd_run.py#L120)
> **Since:** unreleased

```python
def run_destroy_cmd(*, auto_approve: bool = False, var_file: Path | None = None, init_mode: InitMode = <InitMode.AUTO: 'auto'>) -> None:
    ...
```

Run destroy across multiple run directories.

**CLI Options:**

| Flag | Type | Default | Env Var | Description |
|---|---|---|---|---|
| `--auto-approve` | `bool` | `False` | - | Skip interactive approval prompts |
| `--var-file`, `-f` | `Path | None` | `None` | - | Path to a terraform .tfvars file |
| `--init-mode`, `-I` | `InitMode` | `<InitMode.AUTO: 'auto'>` | `TFDO_INIT_MODE` | Init behavior: auto (run init on error related to init), always (run init first), never (skip init) [auto, always, never] |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext run_destroy_cmd_def === -->
<!-- === DO_NOT_EDIT: pkg-ext run_init_cmd_def === -->
<a id="run_init_cmd_def"></a>

### cli_command: `run_init_cmd`
- [source](../../tfdo/_internal/run/cmd_run.py#L70)
> **Since:** unreleased

```python
def run_init_cmd(*, extra_args: list[str] | None = None) -> None:
    ...
```

Run init across multiple run directories.

**CLI Options:**

| Flag | Type | Default | Description |
|---|---|---|---|
| `--extra-args` | `list[str] | None` | `None` | Extra arguments forwarded to terraform init (e.g. --extra-args=-upgrade) |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext run_init_cmd_def === -->
<!-- === DO_NOT_EDIT: pkg-ext run_plan_cmd_def === -->
<a id="run_plan_cmd_def"></a>

### cli_command: `run_plan_cmd`
- [source](../../tfdo/_internal/run/cmd_run.py#L84)
> **Since:** unreleased

```python
def run_plan_cmd(*, var_file: Path | None = None, init_mode: InitMode = <InitMode.AUTO: 'auto'>, out: Path | None = None, json_output: bool = False) -> None:
    ...
```

Run plan across multiple run directories.

**CLI Options:**

| Flag | Type | Default | Env Var | Description |
|---|---|---|---|---|
| `--var-file`, `-f` | `Path | None` | `None` | - | Path to a terraform .tfvars file |
| `--init-mode`, `-I` | `InitMode` | `<InitMode.AUTO: 'auto'>` | `TFDO_INIT_MODE` | Init behavior: auto (run init on error related to init), always (run init first), never (skip init) [auto, always, never] |
| `-o`, `--out` | `Path | None` | `None` | - | Write plan output to file (per run directory) |
| `--json` | `bool` | `False` | - | Output in JSON format |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext run_plan_cmd_def === -->