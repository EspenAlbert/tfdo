<!-- === DO_NOT_EDIT: pkg-ext header === -->
# hooks

<!-- === OK_EDIT: pkg-ext header === -->

<!-- === DO_NOT_EDIT: pkg-ext symbols === -->
- [`ExitEvent`](#exitevent_def)
- [`HookEnvVars`](#hookenvvars_def)
- [`HookInput`](#hookinput_def)
- [`InputModification`](#inputmodification_def)
- [`RetryEvent`](#retryevent_def)
<!-- === OK_EDIT: pkg-ext symbols === -->

<!-- === DO_NOT_EDIT: pkg-ext symbol_details_header === -->
## Symbol Details
<!-- === OK_EDIT: pkg-ext symbol_details_header === -->

<!-- === DO_NOT_EDIT: pkg-ext exitevent_def === -->
<a id="exitevent_def"></a>

### class: `ExitEvent`
- [source](https://github.com/EspenAlbert/tfdo/blob/main/tfdo/_internal/hooks/models.py#L26)
> **Since:** 0.6.0

```python
class ExitEvent(BaseModel):
    reason: str
```

| Field | Type | Default | Since |
|---|---|---|---|
| reason | `str` | - | 0.6.0 |

### Changes

| Version | Change |
|---------|--------|
| 0.6.0 | Made public |
<!-- === OK_EDIT: pkg-ext exitevent_def === -->
<!-- === DO_NOT_EDIT: pkg-ext hookenvvars_def === -->
<a id="hookenvvars_def"></a>

### class: `HookEnvVars`
- [source](https://github.com/EspenAlbert/tfdo/blob/main/tfdo/_internal/hooks/models.py#L9)
> **Since:** 0.6.0

```python
class HookEnvVars(dict):
    ...
```

### Changes

| Version | Change |
|---------|--------|
| 0.6.0 | Made public |
<!-- === OK_EDIT: pkg-ext hookenvvars_def === -->
<!-- === DO_NOT_EDIT: pkg-ext hookinput_def === -->
<a id="hookinput_def"></a>

### class: `HookInput`
- [source](https://github.com/EspenAlbert/tfdo/blob/main/tfdo/_internal/hooks/models.py#L19)
> **Since:** 0.6.0

```python
class HookInput(BaseModel):
    env_vars: HookEnvVars
```

| Field | Type | Default | Since |
|---|---|---|---|
| env_vars | `HookEnvVars` | - | 0.6.0 |

### Changes

| Version | Change |
|---------|--------|
| 0.6.0 | Made public |
<!-- === OK_EDIT: pkg-ext hookinput_def === -->
<!-- === DO_NOT_EDIT: pkg-ext inputmodification_def === -->
<a id="inputmodification_def"></a>

### class: `InputModification`
- [source](https://github.com/EspenAlbert/tfdo/blob/main/tfdo/_internal/hooks/models.py#L30)
> **Since:** 0.6.0

```python
class InputModification(BaseModel):
    env_vars: dict[str, str] = ...
    extra_var_files: list[str] = ...
    extra_args: list[str] = ...
```

| Field | Type | Default | Since |
|---|---|---|---|
| env_vars | `dict[str, str]` | `...` | 0.6.0 |
| extra_var_files | `list[str]` | `...` | 0.6.0 |
| extra_args | `list[str]` | `...` | 0.6.0 |

### Changes

| Version | Change |
|---------|--------|
| 0.6.0 | Made public |
<!-- === OK_EDIT: pkg-ext inputmodification_def === -->
<!-- === DO_NOT_EDIT: pkg-ext retryevent_def === -->
<a id="retryevent_def"></a>

### class: `RetryEvent`
- [source](https://github.com/EspenAlbert/tfdo/blob/main/tfdo/_internal/hooks/models.py#L36)
> **Since:** 0.6.0

```python
class RetryEvent(BaseModel):
    reason: str
```

| Field | Type | Default | Since |
|---|---|---|---|
| reason | `str` | - | 0.6.0 |

### Changes

| Version | Change |
|---------|--------|
| 0.6.0 | Made public |
<!-- === OK_EDIT: pkg-ext retryevent_def === -->