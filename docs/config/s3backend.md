# S3Backend

<!-- === DO_NOT_EDIT: pkg-ext s3backend_def === -->
## class: S3Backend
- [source](https://github.com/EspenAlbert/tfdo/blob/main/tfdo/_internal/config/config_model.py#L24)
> **Since:** 0.6.0

```python
class S3Backend(BaseModel):
    type: Literal[s3] = <BackendType.S3: 's3'>
    bucket: str
    key: str
    region: str | None = None
    dynamodb_table: str | None = None
    encrypt: bool | None = None
    use_lockfile: bool | None = None
```
<!-- === OK_EDIT: pkg-ext s3backend_def === -->

### Fields

| Field | Type | Default | Since |
|---|---|---|---|
| type | `Literal[s3]` | `<BackendType.S3: 's3'>` | 0.6.0 |
| bucket | `str` | - | 0.6.0 |
| key | `str` | - | 0.6.0 |
| region | `str | None` | `None` | 0.6.0 |
| dynamodb_table | `str | None` | `None` | 0.6.0 |
| encrypt | `bool | None` | `None` | 0.6.0 |
| use_lockfile | `bool | None` | `None` | unreleased |

<!-- === DO_NOT_EDIT: pkg-ext s3backend_changes === -->
### Changes

| Version | Change |
|---------|--------|
| unreleased | added optional field 'use_lockfile' (default: None) |
| 0.6.0 | Made public |
<!-- === OK_EDIT: pkg-ext s3backend_changes === -->