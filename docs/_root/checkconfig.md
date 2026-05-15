# CheckConfig

<!-- === DO_NOT_EDIT: pkg-ext checkconfig_def === -->
## class: CheckConfig
- [source](https://github.com/EspenAlbert/tfdo/blob/main/tfdo/_internal/settings.py#L133)
> **Since:** 0.3.0

```python
class CheckConfig(BaseModel):
    tflint: bool = False
    skip_check_providers: bool = False
```
<!-- === OK_EDIT: pkg-ext checkconfig_def === -->

### Fields

| Field | Type | Default | Since |
|---|---|---|---|
| tflint | `bool` | `False` | 0.3.0 |
| skip_check_providers | `bool` | `False` | unreleased |

<!-- === DO_NOT_EDIT: pkg-ext checkconfig_changes === -->
### Changes

| Version | Change |
|---------|--------|
| unreleased | added optional field 'skip_check_providers' (default: False) |
| 0.3.0 | Made public |
<!-- === OK_EDIT: pkg-ext checkconfig_changes === -->