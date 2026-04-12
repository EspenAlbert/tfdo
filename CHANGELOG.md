# Changelog

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
