<!-- === DO_NOT_EDIT: pkg-ext header === -->
# config

<!-- === OK_EDIT: pkg-ext header === -->

<!-- === DO_NOT_EDIT: pkg-ext symbols === -->
- [`BackendType`](#backendtype_def)
- [`DependencyRef`](#dependencyref_def)
- [`HookConfig`](#hookconfig_def)
- [`HookOnError`](#hookonerror_def)
- [`LifecycleEvent`](#lifecycleevent_def)
- [`LocalBackend`](#localbackend_def)
- [`S3Backend`](#s3backend_def)
- [`TagsInject`](#tagsinject_def)
- [`TfDoConfig`](#tfdoconfig_def)
- [`show_cmd`](#show_cmd_def)
<!-- === OK_EDIT: pkg-ext symbols === -->

<!-- === DO_NOT_EDIT: pkg-ext symbol_details_header === -->
## Symbol Details
<!-- === OK_EDIT: pkg-ext symbol_details_header === -->

<!-- === DO_NOT_EDIT: pkg-ext backendtype_def === -->
<a id="backendtype_def"></a>

### class: `BackendType`
- [source](../../tfdo/_internal/config/enums.py#L29)
> **Since:** unreleased

```python
class BackendType(StrEnum):
    ...
```

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext backendtype_def === -->
<!-- === DO_NOT_EDIT: pkg-ext dependencyref_def === -->
<a id="dependencyref_def"></a>

### class: `DependencyRef`
- [source](../../tfdo/_internal/config/config_model.py#L68)
> **Since:** unreleased

```python
class DependencyRef(BaseModel):
    ref: str
    outputs: bool = True
```

| Field | Type | Default | Since |
|---|---|---|---|
| ref | `str` | - | unreleased |
| outputs | `bool` | `True` | unreleased |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext dependencyref_def === -->
<!-- === DO_NOT_EDIT: pkg-ext hookconfig_def === -->
<a id="hookconfig_def"></a>

### class: `HookConfig`
- [source](../../tfdo/_internal/config/config_model.py#L50)
> **Since:** unreleased

```python
class HookConfig(BaseModel):
    name: str
    cmd: str | None = None
    py_locate: str | None = None
    lifecycle_events: list[LifecycleEvent]
    timeout_seconds: int = 30
    priority: int = 5000
    on_error: HookOnError | None = None
```

| Field | Type | Default | Since |
|---|---|---|---|
| name | `str` | - | unreleased |
| cmd | `str | None` | `None` | unreleased |
| py_locate | `str | None` | `None` | unreleased |
| lifecycle_events | `list[LifecycleEvent]` | - | unreleased |
| timeout_seconds | `int` | `30` | unreleased |
| priority | `int` | `5000` | unreleased |
| on_error | `HookOnError | None` | `None` | unreleased |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext hookconfig_def === -->
<!-- === DO_NOT_EDIT: pkg-ext hookonerror_def === -->
<a id="hookonerror_def"></a>

### class: `HookOnError`
- [source](../../tfdo/_internal/config/enums.py#L6)
> **Since:** unreleased

```python
class HookOnError(StrEnum):
    ...
```

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext hookonerror_def === -->
<!-- === DO_NOT_EDIT: pkg-ext lifecycleevent_def === -->
<a id="lifecycleevent_def"></a>

### class: `LifecycleEvent`
- [source](../../tfdo/_internal/config/enums.py#L11)
> **Since:** unreleased

```python
class LifecycleEvent(StrEnum):
    ...
```

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext lifecycleevent_def === -->
<!-- === DO_NOT_EDIT: pkg-ext localbackend_def === -->
<a id="localbackend_def"></a>

### class: `LocalBackend`
- [source](../../tfdo/_internal/config/config_model.py#L38)
> **Since:** unreleased

```python
class LocalBackend(BaseModel):
    type: Literal[local] = <BackendType.LOCAL: 'local'>
    path: str
```

| Field | Type | Default | Since |
|---|---|---|---|
| type | `Literal[local]` | `<BackendType.LOCAL: 'local'>` | unreleased |
| path | `str` | - | unreleased |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext localbackend_def === -->
<!-- === DO_NOT_EDIT: pkg-ext s3backend_def === -->
<a id="s3backend_def"></a>

### class: `S3Backend`
- [source](../../tfdo/_internal/config/config_model.py#L15)
> **Since:** unreleased

```python
class S3Backend(BaseModel):
    type: Literal[s3] = <BackendType.S3: 's3'>
    bucket: str
    key: str
    region: str | None = None
    dynamodb_table: str | None = None
    encrypt: bool | None = None
```

| Field | Type | Default | Since |
|---|---|---|---|
| type | `Literal[s3]` | `<BackendType.S3: 's3'>` | unreleased |
| bucket | `str` | - | unreleased |
| key | `str` | - | unreleased |
| region | `str | None` | `None` | unreleased |
| dynamodb_table | `str | None` | `None` | unreleased |
| encrypt | `bool | None` | `None` | unreleased |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext s3backend_def === -->
<!-- === DO_NOT_EDIT: pkg-ext tagsinject_def === -->
<a id="tagsinject_def"></a>

### class: `TagsInject`
- [source](../../tfdo/_internal/config/enums.py#L41)
> **Since:** unreleased

```python
class TagsInject(StrEnum):
    ...
```

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext tagsinject_def === -->
<!-- === DO_NOT_EDIT: pkg-ext tfdoconfig_def === -->
<a id="tfdoconfig_def"></a>

### class: `TfDoConfig`
- [source](../../tfdo/_internal/config/config_model.py#L73)
> **Since:** unreleased

```python
class TfDoConfig(BaseModel):
    binary: str | None = None
    tf_version: str | None = None
    backend: Annotated[S3Backend | LocalBackend, annotation=NoneType required=True discriminator='type'] | None = None
    check: CheckConfig | None = None
    tags_inject: TagsInject | None = None
    tags: dict[str, str] = ...
    hook_configs: list[HookConfig] = ...
    dependencies: list[DependencyRef] = ...
    var_files: list[str] = ...
    run_dir_discovery: str | None = None
```

| Field | Type | Default | Since |
|---|---|---|---|
| binary | `str | None` | `None` | unreleased |
| tf_version | `str | None` | `None` | unreleased |
| backend | `Annotated[S3Backend | LocalBackend, annotation=NoneType required=True discriminator='type'] | None` | `None` | unreleased |
| check | `CheckConfig | None` | `None` | unreleased |
| tags_inject | `TagsInject | None` | `None` | unreleased |
| tags | `dict[str, str]` | `...` | unreleased |
| hook_configs | `list[HookConfig]` | `...` | unreleased |
| dependencies | `list[DependencyRef]` | `...` | unreleased |
| var_files | `list[str]` | `...` | unreleased |
| run_dir_discovery | `str | None` | `None` | unreleased |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext tfdoconfig_def === -->
<!-- === DO_NOT_EDIT: pkg-ext show_cmd_def === -->
<a id="show_cmd_def"></a>

### cli_command: `show_cmd`
- [source](../../tfdo/_internal/config/cmd_config.py#L59)
> **Since:** unreleased

```python
def show_cmd() -> None:
    ...
```

Print resolved tfdo.yaml config layers and merged result for current work directory.

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext show_cmd_def === -->