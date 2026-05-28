# TfDoUserConfig

<!-- === DO_NOT_EDIT: pkg-ext tfdouserconfig_def === -->
## class: TfDoUserConfig
- [source](../../tfdo/_internal/settings.py#L140)
> **Since:** 0.3.0

```python
class TfDoUserConfig(BaseModel):
    check: CheckConfig | None = None
    plan_display: PlanDisplayOptions | None = None
```
<!-- === OK_EDIT: pkg-ext tfdouserconfig_def === -->

### Fields

| Field | Type | Default | Since |
|---|---|---|---|
| check | `CheckConfig | None` | `None` | 0.3.0 |
| plan_display | `PlanDisplayOptions | None` | `None` | unreleased |

<!-- === DO_NOT_EDIT: pkg-ext tfdouserconfig_changes === -->
### Changes

| Version | Change |
|---------|--------|
| unreleased | added optional field 'plan_display' (default: None) |
| 0.3.0 | Made public |
<!-- === OK_EDIT: pkg-ext tfdouserconfig_changes === -->