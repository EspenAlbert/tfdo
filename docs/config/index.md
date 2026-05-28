<!-- === DO_NOT_EDIT: pkg-ext header === -->
# config

<!-- === OK_EDIT: pkg-ext header === -->

<!-- === DO_NOT_EDIT: pkg-ext symbols === -->
- [`BackendType`](#backendtype_def)
- [`CiConfig`](#ciconfig_def)
- [DependencyRef](./dependencyref.md)
- [`DetailLevel`](#detaillevel_def)
- [`HookConfig`](#hookconfig_def)
- [`HookOnError`](#hookonerror_def)
- [`LifecycleEvent`](#lifecycleevent_def)
- [`LocalBackend`](#localbackend_def)
- [`ModuleConstraint`](#moduleconstraint_def)
- [`ProviderConstraint`](#providerconstraint_def)
- [S3Backend](./s3backend.md)
- [`TagsInject`](#tagsinject_def)
- [TfDoConfig](./tfdoconfig.md)
- [`init_cmd`](#init_cmd_def)
- [`show_cmd`](#show_cmd_def)
<!-- === OK_EDIT: pkg-ext symbols === -->

<!-- === DO_NOT_EDIT: pkg-ext symbol_details_header === -->
## Symbol Details
<!-- === OK_EDIT: pkg-ext symbol_details_header === -->

<!-- === DO_NOT_EDIT: pkg-ext backendtype_def === -->
<a id="backendtype_def"></a>

### class: `BackendType`
- [source](../../tfdo/_internal/config/enums.py#L29)
> **Since:** 0.6.0

```python
class BackendType(StrEnum):
    ...
```

### Changes

| Version | Change |
|---------|--------|
| 0.6.0 | Made public |
<!-- === OK_EDIT: pkg-ext backendtype_def === -->
<!-- === DO_NOT_EDIT: pkg-ext hookconfig_def === -->
<a id="hookconfig_def"></a>

### class: `HookConfig`
- [source](../../tfdo/_internal/config/config_model.py#L81)
> **Since:** 0.6.0

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
| name | `str` | - | 0.6.0 |
| cmd | `str | None` | `None` | 0.6.0 |
| py_locate | `str | None` | `None` | 0.6.0 |
| lifecycle_events | `list[LifecycleEvent]` | - | 0.6.0 |
| timeout_seconds | `int` | `30` | 0.6.0 |
| priority | `int` | `5000` | 0.6.0 |
| on_error | `HookOnError | None` | `None` | 0.6.0 |

### Changes

| Version | Change |
|---------|--------|
| 0.6.0 | Made public |
<!-- === OK_EDIT: pkg-ext hookconfig_def === -->
<!-- === DO_NOT_EDIT: pkg-ext hookonerror_def === -->
<a id="hookonerror_def"></a>

### class: `HookOnError`
- [source](../../tfdo/_internal/config/enums.py#L6)
> **Since:** 0.6.0

```python
class HookOnError(StrEnum):
    ...
```

### Changes

| Version | Change |
|---------|--------|
| 0.6.0 | Made public |
<!-- === OK_EDIT: pkg-ext hookonerror_def === -->
<!-- === DO_NOT_EDIT: pkg-ext lifecycleevent_def === -->
<a id="lifecycleevent_def"></a>

### class: `LifecycleEvent`
- [source](../../tfdo/_internal/config/enums.py#L11)
> **Since:** 0.6.0

```python
class LifecycleEvent(StrEnum):
    ...
```

### Changes

| Version | Change |
|---------|--------|
| 0.6.0 | Made public |
<!-- === OK_EDIT: pkg-ext lifecycleevent_def === -->
<!-- === DO_NOT_EDIT: pkg-ext localbackend_def === -->
<a id="localbackend_def"></a>

### class: `LocalBackend`
- [source](../../tfdo/_internal/config/config_model.py#L69)
> **Since:** 0.6.0

```python
class LocalBackend(BaseModel):
    type: Literal[local] = <BackendType.LOCAL: 'local'>
    path: str
```

| Field | Type | Default | Since |
|---|---|---|---|
| type | `Literal[local]` | `<BackendType.LOCAL: 'local'>` | 0.6.0 |
| path | `str` | - | 0.6.0 |

### Changes

| Version | Change |
|---------|--------|
| 0.6.0 | Made public |
<!-- === OK_EDIT: pkg-ext localbackend_def === -->
<!-- === DO_NOT_EDIT: pkg-ext tagsinject_def === -->
<a id="tagsinject_def"></a>

### class: `TagsInject`
- [source](../../tfdo/_internal/config/enums.py#L41)
> **Since:** 0.6.0

```python
class TagsInject(StrEnum):
    ...
```

### Changes

| Version | Change |
|---------|--------|
| 0.6.0 | Made public |
<!-- === OK_EDIT: pkg-ext tagsinject_def === -->
<!-- === DO_NOT_EDIT: pkg-ext show_cmd_def === -->
<a id="show_cmd_def"></a>

### cli_command: `show_cmd`
- [source](../../tfdo/_internal/config/cmd_config.py#L59)
> **Since:** 0.6.0

```python
def show_cmd() -> None:
    ...
```

Print resolved tfdo.yaml config layers and merged result for current work directory.

### Changes

| Version | Change |
|---------|--------|
| 0.6.0 | Made public |
<!-- === OK_EDIT: pkg-ext show_cmd_def === -->
<!-- === DO_NOT_EDIT: pkg-ext init_cmd_def === -->
<a id="init_cmd_def"></a>

### cli_command: `init_cmd`
- [source](../../tfdo/_internal/config/cmd_config.py#L73)
> **Since:** 0.6.0

```python
def init_cmd(*, dry_run: bool = False) -> None:
    ...
```

Detect run directories and generate a starter tfdo.yaml.

**CLI Options:**

| Flag | Type | Default | Description |
|---|---|---|---|
| `--dry-run` | `bool` | `False` | Preview detected directories without writing tfdo.yaml |

### Changes

| Version | Change |
|---------|--------|
| 0.6.0 | Made public |
<!-- === OK_EDIT: pkg-ext init_cmd_def === -->
<!-- === DO_NOT_EDIT: pkg-ext ciconfig_def === -->
<a id="ciconfig_def"></a>

### class: `CiConfig`
- [source](../../tfdo/_internal/config/config_model.py#L128)
> **Since:** 0.7.0

```python
class CiConfig(BaseModel):
    oidc: bool = False
    repo_org: str | None = None
    repo_name: str | None = None
    oidc_roles: dict[str, str] = ...
    tfdo_install: str = 'git+https://github.com/EspenAlbert/tfdo.git@main'
```

| Field | Type | Default | Since |
|---|---|---|---|
| oidc | `bool` | `False` | 0.7.0 |
| repo_org | `str | None` | `None` | 0.7.0 |
| repo_name | `str | None` | `None` | 0.7.0 |
| oidc_roles | `dict[str, str]` | `...` | 0.7.0 |
| tfdo_install | `str` | `'git+https://github.com/EspenAlbert/tfdo.git@main'` | 0.7.0 |

### Changes

| Version | Change |
|---------|--------|
| 0.7.0 | Made public |
<!-- === OK_EDIT: pkg-ext ciconfig_def === -->
<!-- === DO_NOT_EDIT: pkg-ext moduleconstraint_def === -->
<a id="moduleconstraint_def"></a>

### class: `ModuleConstraint`
- [source](../../tfdo/_internal/config/config_model.py#L114)
> **Since:** 0.7.0

```python
class ModuleConstraint(BaseModel):
    source: str
    constraint: str | None = None
```

| Field | Type | Default | Since |
|---|---|---|---|
| source | `str` | - | 0.7.0 |
| constraint | `str | None` | `None` | 0.7.0 |

### Changes

| Version | Change |
|---------|--------|
| 0.7.0 | Made public |
<!-- === OK_EDIT: pkg-ext moduleconstraint_def === -->
<!-- === DO_NOT_EDIT: pkg-ext providerconstraint_def === -->
<a id="providerconstraint_def"></a>

### class: `ProviderConstraint`
- [source](../../tfdo/_internal/config/config_model.py#L108)
> **Since:** 0.7.0

```python
class ProviderConstraint(BaseModel):
    name: str
    source: str | None = None
    constraint: str | None = None
```

| Field | Type | Default | Since |
|---|---|---|---|
| name | `str` | - | 0.7.0 |
| source | `str | None` | `None` | 0.7.0 |
| constraint | `str | None` | `None` | 0.7.0 |

### Changes

| Version | Change |
|---------|--------|
| 0.7.0 | Made public |
<!-- === OK_EDIT: pkg-ext providerconstraint_def === -->
<!-- === DO_NOT_EDIT: pkg-ext detaillevel_def === -->
<a id="detaillevel_def"></a>

### class: `DetailLevel`
- [source](../../tfdo/_internal/output/plan_display.py#L12)
> **Since:** 0.8.0

```python
class DetailLevel(StrEnum):
    ...
```

### Changes

| Version | Change |
|---------|--------|
| 0.8.0 | Made public |
<!-- === OK_EDIT: pkg-ext detaillevel_def === -->