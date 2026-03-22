<!-- === DO_NOT_EDIT: pkg-ext header === -->
# __ROOT__

<!-- === OK_EDIT: pkg-ext header === -->

<!-- === DO_NOT_EDIT: pkg-ext symbols === -->
- [`CheckConfig`](#checkconfig_def)
- [`InteractiveMode`](#interactivemode_def)
- [TfDoSettings](./tfdosettings.md)
- [`TfDoUserConfig`](#tfdouserconfig_def)
- [`get_settings`](#get_settings_def)
- [`info_cmd`](#info_cmd_def)
- [`main_callback`](#main_callback_def)
<!-- === OK_EDIT: pkg-ext symbols === -->

<!-- === DO_NOT_EDIT: pkg-ext symbol_details_header === -->
## Symbol Details
<!-- === OK_EDIT: pkg-ext symbol_details_header === -->

<!-- === DO_NOT_EDIT: pkg-ext get_settings_def === -->
<a id="get_settings_def"></a>

### cli_command: `get_settings`
- [source](../../tfdo/_internal/typer_app.py#L46)
> **Since:** 0.1.0

```python
def get_settings() -> TfDoSettings:
    ...
```

### Changes

| Version | Change |
|---------|--------|
| 0.1.0 | Made public |
<!-- === OK_EDIT: pkg-ext get_settings_def === -->
<!-- === DO_NOT_EDIT: pkg-ext main_callback_def === -->
<a id="main_callback_def"></a>

### cli_command: `main_callback`
- [source](../../tfdo/_internal/typer_app.py#L15)
> **Since:** 0.1.0

```python
def main_callback(*, binary: str = 'terraform', tf_version: str | None = ..., work_dir: Path | None = ..., interactive: InteractiveMode = <InteractiveMode.AUTO: 'auto'>, log_level: str = 'INFO', passthrough: bool = False) -> None:
    ...
```

**CLI Options:**

| Flag | Type | Default | Env Var | Description |
|---|---|---|---|---|
| `-b`, `--binary` | `str` | `'terraform'` | `TFDO_BINARY` | Terraform binary name or path |
| `-V`, `--tf-version` | `str | None` | *required* | `TFDO_TF_VERSION` | Terraform version (uses mise for version selection) |
| `-w`, `--work-dir` | `Path | None` | *required* | `TFDO_WORK_DIR` | Working directory for terraform commands |
| `--interactive` | `InteractiveMode` | `<InteractiveMode.AUTO: 'auto'>` | `TFDO_INTERACTIVE` | Interactive mode: auto (detect TTY), always (force stdin), never (no stdin) [auto, always, never] |
| `--log-level` | `str` | `'INFO'` | - | Log level for tfdo |
| `--passthrough` | `bool` | `False` | - | Disable parsed output, pass raw ANSI from terraform |

### Changes

| Version | Change |
|---------|--------|
| 0.1.0 | Made public |
<!-- === OK_EDIT: pkg-ext main_callback_def === -->
<!-- === DO_NOT_EDIT: pkg-ext interactivemode_def === -->
<a id="interactivemode_def"></a>

### class: `InteractiveMode`
- [source](../../tfdo/_internal/settings.py#L20)
> **Since:** 0.2.0

```python
class InteractiveMode(StrEnum):
    ...
```

### Changes

| Version | Change |
|---------|--------|
| 0.2.0 | Made public |
<!-- === OK_EDIT: pkg-ext interactivemode_def === -->
<!-- === DO_NOT_EDIT: pkg-ext checkconfig_def === -->
<a id="checkconfig_def"></a>

### class: `CheckConfig`
- [source](../../tfdo/_internal/settings.py#L73)
> **Since:** unreleased

```python
class CheckConfig(BaseModel):
    tflint: bool = False
```

| Field | Type | Default | Since |
|---|---|---|---|
| tflint | `bool` | `False` | unreleased |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext checkconfig_def === -->
<!-- === DO_NOT_EDIT: pkg-ext tfdouserconfig_def === -->
<a id="tfdouserconfig_def"></a>

### class: `TfDoUserConfig`
- [source](../../tfdo/_internal/settings.py#L77)
> **Since:** unreleased

```python
class TfDoUserConfig(BaseModel):
    check: CheckConfig | None = None
```

| Field | Type | Default | Since |
|---|---|---|---|
| check | `CheckConfig | None` | `None` | unreleased |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext tfdouserconfig_def === -->
<!-- === DO_NOT_EDIT: pkg-ext info_cmd_def === -->
<a id="info_cmd_def"></a>

### cli_command: `info_cmd`
- [source](../../tfdo/_internal/core/cmd_info.py#L39)
> **Since:** unreleased

```python
def info_cmd() -> None:
    ...
```

Show resolved settings, paths, and user config.

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext info_cmd_def === -->