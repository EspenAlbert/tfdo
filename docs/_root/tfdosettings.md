# TfDoSettings

<!-- === DO_NOT_EDIT: pkg-ext tfdosettings_def === -->
## class: TfDoSettings
- [source](https://github.com/EspenAlbert/tfdo/blob/main/tfdo/_internal/settings.py#L30)
> **Since:** 0.1.0

```python
class TfDoSettings(StaticSettings):
    STATIC_DIR: Path | None = None
    CACHE_DIR: Path | None = None
    SKIP_APP_NAME: bool = False
    binary: str = 'terraform'
    tf_version: str | None = None
    work_dir: Path = ...
    interactive: InteractiveMode = <InteractiveMode.AUTO: 'auto'>
    log_level: str = 'INFO'
    passthrough: bool = False
    verbose_shell: bool = False
    backends_dirs_raw: str | None = None
    provider_hints_path: Path | None = None
    env_vars_dirs_raw: str | None = None
```
<!-- === OK_EDIT: pkg-ext tfdosettings_def === -->

### Environment Variables

| Variable | Field | Type | Default |
|----------|-------|------|---------|
| `static_dir` | `STATIC_DIR` | Path | None | None |
| `cache_dir` | `CACHE_DIR` | Path | None | None |
| `skip_app_name` | `SKIP_APP_NAME` | bool | False |
| `tfdo_binary` | `binary` | str | 'terraform' |
| `binary` | `binary` | str | 'terraform' |
| `tfdo_tf_version` | `tf_version` | str | None | None |
| `tf_version` | `tf_version` | str | None | None |

### Fields

| Field | Type | Default | Since | Description |
|---|---|---|---|---|
| STATIC_DIR | `Path | None` | `None` | unreleased | - |
| CACHE_DIR | `Path | None` | `None` | unreleased | - |
| SKIP_APP_NAME | `bool` | `False` | unreleased | - |
| binary | `str` | `'terraform'` | unreleased | Terraform binary name or path (terraform, tofu, etc.) |
| tf_version | `str | None` | `None` | unreleased | When set, binary becomes 'mise x terraform@{version} -- {binary}' |

<!-- === DO_NOT_EDIT: pkg-ext tfdosettings_changes === -->
### Changes

| Version | Change |
|---------|--------|
| unreleased | added optional field 'verbose_shell' (default: False) |
| unreleased | added optional field 'provider_hints_path' (default: None) |
| unreleased | added optional field 'env_vars_dirs_raw' (default: None) |
| unreleased | added optional field 'backends_dirs_raw' (default: None) |
| 0.2.0 | added optional field 'interactive' (default: <InteractiveMode.AUTO: 'auto'>) |
| 0.1.1 | added optional field 'work_dir' (default: ...) |
| 0.1.0 | Made public |
<!-- === OK_EDIT: pkg-ext tfdosettings_changes === -->