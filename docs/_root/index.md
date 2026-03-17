<!-- === DO_NOT_EDIT: pkg-ext header === -->
# __ROOT__

<!-- === OK_EDIT: pkg-ext header === -->

<!-- === DO_NOT_EDIT: pkg-ext symbols === -->
- [TfDoSettings](./tfdosettings.md)
- [`get_settings`](#get_settings_def)
- [`main_callback`](#main_callback_def)
<!-- === OK_EDIT: pkg-ext symbols === -->

<!-- === DO_NOT_EDIT: pkg-ext symbol_details_header === -->
## Symbol Details
<!-- === OK_EDIT: pkg-ext symbol_details_header === -->

<!-- === DO_NOT_EDIT: pkg-ext get_settings_def === -->
<a id="get_settings_def"></a>

### cli_command: `get_settings`
- [source](../../tfdo/_internal/typer_app.py#L35)
> **Since:** unreleased

```python
def get_settings() -> TfDoSettings:
    ...
```

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext get_settings_def === -->
<!-- === DO_NOT_EDIT: pkg-ext main_callback_def === -->
<a id="main_callback_def"></a>

### cli_command: `main_callback`
- [source](../../tfdo/_internal/typer_app.py#L13)
> **Since:** unreleased

```python
def main_callback(*, binary: str = 'terraform', tf_version: str | None = ..., log_level: str = 'INFO', passthrough: bool = False) -> None:
    ...
```

**CLI Options:**

| Flag | Type | Default | Env Var | Description |
|---|---|---|---|---|
| `-b`, `--binary` | `str` | `'terraform'` | `TFDO_BINARY` | Terraform binary name or path |
| `-V`, `--tf-version` | `str | None` | *required* | `TFDO_TF_VERSION` | Terraform version (uses mise for version selection) |
| `--log-level` | `str` | `'INFO'` | - | Log level for tfdo |
| `--passthrough` | `bool` | `False` | - | Disable parsed output, pass raw ANSI from terraform |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext main_callback_def === -->