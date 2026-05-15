# DependencyRef

<!-- === DO_NOT_EDIT: pkg-ext dependencyref_def === -->
## class: DependencyRef
- [source](../../tfdo/_internal/config/config_model.py#L99)
> **Since:** 0.6.0

```python
class DependencyRef(BaseModel):
    ref: str
    outputs: dict[str, str] = ...
    outputs_mock: dict[str, str] = ...
```
<!-- === OK_EDIT: pkg-ext dependencyref_def === -->

### Fields

| Field | Type | Default | Since |
|---|---|---|---|
| ref | `str` | - | 0.6.0 |
| outputs | `dict[str, str]` | `...` | unreleased |
| outputs_mock | `dict[str, str]` | `...` | unreleased |

<!-- === DO_NOT_EDIT: pkg-ext dependencyref_changes === -->
### Changes

| Version | Change |
|---------|--------|
| unreleased | field 'outputs' default: True -> ... |
| unreleased | field 'outputs' type: bool -> dict[str, str] |
| unreleased | added optional field 'outputs_mock' (default: ...) |
| 0.6.0 | Made public |
<!-- === OK_EDIT: pkg-ext dependencyref_changes === -->