# Changelog

## 0.9.0 2026-05-29T10-53Z

### __Root__
- `__ROOT__.TfDoUserConfig`: added optional field 'apply_display' (default: None)

### Config
- New class `ApplyDisplayOptions`

### Core
- fix: Skip apply prompt when plan has no applyable changes [aad214](https://github.com/EspenAlbert/tfdo/commit/aad214)


## 0.8.2 2026-05-28T18-42Z

### Other Changes
- Chore: support output errors during plan/apply/destroy


## 0.8.1 2026-05-28T09-35Z

### Core
- fix(output): Accept structured after_unknown on output changes [6defd3](https://github.com/EspenAlbert/tfdo/commit/6defd3)


## 0.8.0 2026-05-28T06-45Z

### __Root__
- `__ROOT__.TfDoUserConfig`: added optional field 'plan_display' (default: None)

### Config
- New class `DetailLevel`


## 0.7.0 2026-05-15T16-46Z

### __Root__
- `__ROOT__.CheckConfig`: added optional field 'skip_check_providers' (default: False)
- `__ROOT__.TfDoSettings`: added optional field 'backends_dirs_raw' (default: None)
- `__ROOT__.TfDoSettings`: added optional field 'env_vars_dirs_raw' (default: None)
- `__ROOT__.TfDoSettings`: added optional field 'provider_hints_path' (default: None)
- `__ROOT__.TfDoSettings`: added optional field 'verbose_shell' (default: False)

### Boot
- New function `boot_cmd`

### Config
- BREAKING `config.DependencyRef`: field 'outputs' type: bool -> dict[str, str]
- BREAKING `config.TfDoConfig`: field 'run_dir_discovery' type: str | None -> str
- New class `ProviderConstraint`
- New class `ModuleConstraint`
- New class `CiConfig`
- `config.DependencyRef`: added optional field 'outputs_mock' (default: ...)
- `config.DependencyRef`: field 'outputs' default: True -> ...
- `config.S3Backend`: added optional field 'use_lockfile' (default: None)
- `config.TfDoConfig`: added optional field 'ci' (default: None)
- `config.TfDoConfig`: added optional field 'env_var_files' (default: ...)
- `config.TfDoConfig`: added optional field 'modules' (default: ...)
- `config.TfDoConfig`: added optional field 'providers' (default: ...)
- `config.TfDoConfig`: field 'run_dir_discovery' default: None -> 'envs/{env}/{run_dir}'

### Copy
- New function `env_cmd`

### New
- New function `backend_cmd`
- New function `run_dir_cmd`

### Sync
- New function `justfile_cmd`
- New function `github_cmd`


## 0.6.0 2026-04-12T17-41Z

### Config
- New function `show_cmd`
- New class `HookOnError`
- New class `LifecycleEvent`
- New class `BackendType`
- New class `TagsInject`
- New class `S3Backend`
- New class `LocalBackend`
- New class `HookConfig`
- New class `DependencyRef`
- New class `TfDoConfig`
- New function `init_cmd`

### Hooks
- New class `HookEnvVars`
- New class `HookInput`
- New class `ExitEvent`
- New class `InputModification`
- New class `RetryEvent`

### Run
- New function `run_callback`
- New function `run_init_cmd`
- New function `run_plan_cmd`
- New function `run_apply_cmd`
- New function `run_destroy_cmd`


## 0.5.0 2026-03-25T22-01Z

### Inspect
- New function `inspect_api_coverage_cmd`
- New class `SchemaSearchRowsBehavior`
- New class `SchemaSearch`
- New class `MatchingAttributeDescription`
- New class `MatchingSchemaResource`


## 0.4.0 2026-03-24T10-26Z

### Inspect
- New function `inspect_hcl_paths_cmd`
- New function `inspect_resource_usage_cmd`

### Schema
- New function `schema_show_cmd`
- New function `schema_diff_cmd`
- New class `ResourceSchemaChange`
- New class `SchemaDiffResult`


## 0.3.0 2026-03-22T21-01Z

### __Root__
- New function `info_cmd`
- New class `CheckConfig`
- New class `TfDoUserConfig`


## 0.2.0 2026-03-19T08-39Z

### __Root__
- New class `InteractiveMode`
- `__ROOT__.TfDoSettings`: added optional field 'interactive' (default: <InteractiveMode.AUTO: 'auto'>)

### Core
- New class `InitMode`


## 0.1.1 2026-03-18T07-45Z

### __Root__
- `__ROOT__.TfDoSettings`: added optional field 'work_dir' (default: ...)


## 0.1.0 2026-03-17T21-46Z

### __Root__
- New function `main_callback`
- New function `get_settings`
- New class `TfDoSettings`

### Core
- New function `plan_cmd`
- New function `init_cmd`
- New function `destroy_cmd`
- New function `check_cmd`
- New function `apply_cmd`
