# Orchestration rendering CI fixture

Credential-free staging layout (`envs/staging/{networking,compute,database}`) for live `terraform plan` and `apply` orchestration smoke. Uses `hashicorp/random` and `hashicorp/time` only; state under `/tmp/tfdo-orchestration/`.

**Canonical source:** `code/00_debug/13_orchestration_rendering` in the py-src workspace. Re-copy HCL and `tfdo.yaml` into this directory before PR when the manual fixture changes.

## Local / CI

From tfdo repo root:

```sh
just orchestration-fixture-init
just orchestration-smoke
```

CI job **`orchestration-smoke`** runs init, then plan, then `apply --auto-approve`. Plan treats exit code 0 or 2 as success; apply must exit 0. Open the Actions log to review orchestration lines manually.

## Staging waves

```text
wave 0: envs/staging/compute, envs/staging/networking
wave 1: envs/staging/database
```

`database` depends on networking and compute for wave ordering only.
