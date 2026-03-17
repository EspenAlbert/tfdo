# TfDoSettings

<!-- === DO_NOT_EDIT: pkg-ext tfdosettings_def === -->
## class: TfDoSettings
- [source](../../tfdo/_internal/settings.py#L9)
> **Since:** unreleased

```python
class TfDoSettings(StaticSettings):
    STATIC_DIR: Path | None = None
    CACHE_DIR: Path | None = None
    SKIP_APP_NAME: bool = False
    binary: str = 'terraform'
    tf_version: str | None = None
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
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext tfdosettings_changes === -->