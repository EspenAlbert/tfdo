# TfDoConfig

<!-- === DO_NOT_EDIT: pkg-ext tfdoconfig_def === -->
## class: TfDoConfig
- [source](https://github.com/EspenAlbert/tfdo/blob/main/tfdo/_internal/config/config_model.py#L136)
> **Since:** 0.6.0

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
    run_dir_discovery: str = 'envs/{env}/{run_dir}'
    providers: list[ProviderConstraint] = ...
    modules: list[ModuleConstraint] = ...
    env_var_files: list[str] = ...
    ci: CiConfig | None = None
```
<!-- === OK_EDIT: pkg-ext tfdoconfig_def === -->

### Fields

| Field | Type | Default | Since |
|---|---|---|---|
| binary | `str | None` | `None` | 0.6.0 |
| tf_version | `str | None` | `None` | 0.6.0 |
| backend | `Annotated[S3Backend | LocalBackend, annotation=NoneType required=True discriminator='type'] | None` | `None` | 0.6.0 |
| check | `CheckConfig | None` | `None` | 0.6.0 |
| tags_inject | `TagsInject | None` | `None` | 0.6.0 |
| tags | `dict[str, str]` | `...` | 0.6.0 |
| hook_configs | `list[HookConfig]` | `...` | 0.6.0 |
| dependencies | `list[DependencyRef]` | `...` | 0.6.0 |
| var_files | `list[str]` | `...` | 0.6.0 |
| run_dir_discovery | `str` | `'envs/{env}/{run_dir}'` | unreleased |
| providers | `list[ProviderConstraint]` | `...` | unreleased |
| modules | `list[ModuleConstraint]` | `...` | unreleased |
| env_var_files | `list[str]` | `...` | unreleased |
| ci | `CiConfig | None` | `None` | unreleased |

<!-- === DO_NOT_EDIT: pkg-ext tfdoconfig_changes === -->
### Changes

| Version | Change |
|---------|--------|
| unreleased | field 'run_dir_discovery' default: None -> 'envs/{env}/{run_dir}' |
| unreleased | field 'run_dir_discovery' type: str | None -> str |
| unreleased | added optional field 'providers' (default: ...) |
| unreleased | added optional field 'modules' (default: ...) |
| unreleased | added optional field 'env_var_files' (default: ...) |
| unreleased | added optional field 'ci' (default: None) |
| 0.6.0 | Made public |
<!-- === OK_EDIT: pkg-ext tfdoconfig_changes === -->