<!-- === DO_NOT_EDIT: pkg-ext header === -->
# config

<!-- === OK_EDIT: pkg-ext header === -->

<!-- === DO_NOT_EDIT: pkg-ext symbols === -->
- [`BackendType`](#backendtype_def)
- [`CiConfig`](#ciconfig_def)
- [DependencyRef](./dependencyref.md)
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
- [source](https://github.com/EspenAlbert/tfdo/blob/main/tfdo/_internal/config/enums.py#L29)
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
- [source](https://github.com/EspenAlbert/tfdo/blob/main/tfdo/_internal/config/config_model.py#L81)
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
- [source](https://github.com/EspenAlbert/tfdo/blob/main/tfdo/_internal/config/enums.py#L6)
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
- [source](https://github.com/EspenAlbert/tfdo/blob/main/tfdo/_internal/config/enums.py#L11)
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
- [source](https://github.com/EspenAlbert/tfdo/blob/main/tfdo/_internal/config/config_model.py#L69)
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
- [source](https://github.com/EspenAlbert/tfdo/blob/main/tfdo/_internal/config/enums.py#L41)
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
- [source](https://github.com/EspenAlbert/tfdo/blob/main/tfdo/_internal/config/cmd_config.py#L59)
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
- [source](https://github.com/EspenAlbert/tfdo/blob/main/tfdo/_internal/config/cmd_config.py#L73)
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
- [source](https://github.com/EspenAlbert/tfdo/blob/main/tfdo/_internal/config/config_model.py#L128)
> **Since:** unreleased

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
| oidc | `bool` | `False` | unreleased |
| repo_org | `str | None` | `None` | unreleased |
| repo_name | `str | None` | `None` | unreleased |
| oidc_roles | `dict[str, str]` | `...` | unreleased |
| tfdo_install | `str` | `'git+https://github.com/EspenAlbert/tfdo.git@main'` | unreleased |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext ciconfig_def === -->
<!-- === DO_NOT_EDIT: pkg-ext moduleconstraint_def === -->
<a id="moduleconstraint_def"></a>

### class: `ModuleConstraint`
- [source](https://github.com/EspenAlbert/tfdo/blob/main/tfdo/_internal/config/config_model.py#L114)
> **Since:** unreleased

```python
class ModuleConstraint(BaseModel):
    source: str
    constraint: str | None = None
```

| Field | Type | Default | Since |
|---|---|---|---|
| source | `str` | - | unreleased |
| constraint | `str | None` | `None` | unreleased |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext moduleconstraint_def === -->
<!-- === DO_NOT_EDIT: pkg-ext providerconstraint_def === -->
<a id="providerconstraint_def"></a>

### class: `ProviderConstraint`
- [source](https://github.com/EspenAlbert/tfdo/blob/main/tfdo/_internal/config/config_model.py#L108)
> **Since:** unreleased

```python
class ProviderConstraint(BaseModel):
    name: str
    source: str | None = None
    constraint: str | None = None
```

| Field | Type | Default | Since |
|---|---|---|---|
| name | `str` | - | unreleased |
| source | `str | None` | `None` | unreleased |
| constraint | `str | None` | `None` | unreleased |

### Changes

| Version | Change |
|---------|--------|
| unreleased | Made public |
<!-- === OK_EDIT: pkg-ext providerconstraint_def === -->