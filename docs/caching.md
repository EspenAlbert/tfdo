# Caching

tfdo maintains a per-user cache for two purposes: avoiding repeated provider plugin downloads across repos, and storing module source trees so `tfdo new run-dir` can read module schemas without running `terraform init` inside the run-dir.

Both caches live under `cache_root`, resolved by [`TfDoSettings.cache_root`](../_root/tfdosettings.md). To see the exact path on your machine:

```sh
tfdo info
```

Override the default with the `CACHE_DIR` environment variable (sets the base directory directly, bypassing platformdirs).

---

## Provider plugin cache

Every `terraform init` call tfdo issues passes `TF_PLUGIN_CACHE_DIR` pointing at `{cache_root}/tf_plugins/`. This is Terraform's built-in read-through provider cache: on the first `init`, Terraform downloads the provider binary there; on every subsequent `init` in any repo, it copies from the cache instead of hitting the registry.

tfdo injects this variable automatically in `InitInput._inject_plugin_cache`. You do not need to configure anything. The variable is only set if it is not already present in the environment, so any value you set externally takes precedence.

---

## Module source cache

The module cache stores the `.terraform/modules/` tree for each `(source, version)` pair so the questionnaire in `tfdo new run-dir` can inspect variable and output definitions without touching `.terraform/` inside the run-dir.

### Layout

```
{cache_root}/
  tf_plugins/          # terraform provider binary cache (TF_PLUGIN_CACHE_DIR)
  tf_modules/
    {source_safe}/     # source with / replaced by %2F, e.g. hashicorp%2Fconsul%2Faws
      {version}/       # resolved semver tag, e.g. 0.7.3
        modules.json   # terraform's module manifest
        x/             # module source tree
```

`source_safe` URL-encodes path separators so a multi-segment registry source like `hashicorp/consul/aws` becomes a single directory name `hashicorp%2Fconsul%2Faws`.

### Population

`tfdo boot` calls `module_cache.populate` for each module selected during the boot questionnaire. `populate` works as follows:

1. Check whether `{cache_root}/tf_modules/{source_safe}/{version}/` already exists and contains files. Return immediately on a hit.
2. Write a minimal stub to a tmpdir:
   ```hcl
   module "x" {
     source  = "{source}"
     version = "{version}"   # omitted when version is not pinned
   }
   ```
3. Run `terraform init -no-color -input=false` in the tmpdir. The provider plugin cache is injected automatically via `TF_PLUGIN_CACHE_DIR`, so providers downloaded during module init are shared too.
4. Read `.terraform/modules/modules.json` from the tmpdir and parse the entry with `Key = "x"` to get the registry-resolved version number.
5. Copy `.terraform/modules/` from the tmpdir to `{cache_root}/tf_modules/{source_safe}/{resolved_version}/`.

If `terraform init` exits non-zero, `populate` raises `ValueError` with the stderr output.

### Version resolution and pinning

When `ModuleConstraint.constraint` is set (e.g. `">= 1.0.0"` or `"0.7.3"`), `populate` writes the stub with that constraint and stores the result under the same constraint string as the cache key.

When `constraint` is `None`, tfdo passes the sentinel `UNRESOLVED` and omits the `version =` line from the stub. Terraform picks the latest version from the registry. After init, tfdo reads the resolved version (e.g. `"0.7.3"`) from `modules.json` and stores the tree under that version. `tfdo boot` then writes `constraint: "0.7.3"` back to `tfdo.yaml`, so the project is pinned from the first run and subsequent lookups are stable.

This means there is never a directory named `unresolved` on disk. The sentinel only controls whether the `version =` attribute appears in the stub.

### Read path

`tfdo new run-dir` reads module variable and output definitions directly from `{cache_root}/tf_modules/{source_safe}/{version}/` — no `terraform init` runs inside the run-dir at schema-reading time. On a cache miss (the user runs `new run-dir` without having run `boot` first), the command calls `module_cache.populate` as a safety net before reading.

### Concurrency

There is no lock on the module cache. Concurrent `tfdo boot` runs on the same machine can both attempt to populate the same entry. The worst outcome is a duplicate download; the `shutil.copytree(..., dirs_exist_ok=True)` call is idempotent.
