# tfdo

The outer layer [Terraform](https://developer.hashicorp.com/terraform) and [OpenTofu](https://opentofu.org/) are missing.

`tfdo` replaces the shell scripts, retry hacks, and copy-pasted CI workflows that every Terraform repo accumulates with a single CLI that handles init reliability, plan readability, run-directory orchestration, and CI scaffolding out of the box.

Full reference docs: [espenalbert.github.io/tfdo](https://espenalbert.github.io/tfdo/).

## Why tfdo

Pick any Terraform repo that's grown past one run directory. You'll find the same patterns being rewritten by hand:

- **Flaky `init`**: Registry timeouts and plugin download races fail CI. "Just re-run" becomes the team policy.
- **200-line plan dumps**: Three resources change, buried in 247 lines of refresh output and `(known after apply)`. Nobody reads it.
- **Shell-script CI**: A 180-line `run-terraform.sh` per repo, copy-pasted between teams, nobody wants to touch.
- **Blind provider upgrades**: Bump `v5.x` to `v6.x`, run `plan`, discover 12 breakages.
- **The 50-module PR**: One-line change to a shared variable triggers `plan` in every run directory. 22-minute CI feedback.

`tfdo` ships solutions for the entire list as commands. None of them require restructuring your repo. `cd` into any run directory and `terraform plan` still works.

## What tfdo owns

- **Invocation reliability**: Retry on transient `init` errors, shared `TF_PLUGIN_CACHE_DIR` across repos, `--init-mode auto|always|never`.
- **Run-directory orchestration**: Multi-directory plan/apply with selectors (`--env`, `--team`, `--app`, `--tags`), parallel waves, dependency DAG, and git-diff-based `--changed`.
- **Quality checks**: `tfdo check --fix` runs `fmt + validate + tflint` ruff-style and rewrites in place.
- **Schema intelligence**: `tfdo schema diff` and `tfdo inspect resource-usage` walk cached provider schemas to flag breaking changes and unused attributes before `plan`.
- **CI scaffolding**: `tfdo sync github --oidc` provisions the workflows, env secrets, AWS OIDC provider, and per-env IAM roles end to end.
- **Repo bootstrap**: `tfdo boot` takes an empty folder to a working `tfdo.yaml`, backend, and module cache.

Terraform and OpenTofu still own everything they always did: graph execution, apply semantics, state, locking, and the provider protocol. `tfdo` wraps the binary; it never forks it.

## Install

`tfdo` requires Python 3.13+ and a `terraform` (or `tofu`) binary on `PATH`.

```sh
uv tool install git+https://github.com/EspenAlbert/tfdo.git
# or, with pipx
pipx install git+https://github.com/EspenAlbert/tfdo.git
```

Use a specific binary or version (via [mise](https://mise.jdx.dev/)):

```sh
tfdo --binary tofu plan
tfdo --tf-version 1.9.0 plan       # rewrites to `mise x terraform@1.9.0 -- terraform`
```

## Quickstart

From an empty directory to a CI-wired repo:

```sh
tfdo boot                          # backend + providers + tfdo.yaml + module cache
tfdo new run-dir                   # questionnaire-driven stack (e.g. envs/dev/project)
tfdo check --fix                   # fmt + validate + tflint across all run-dirs
tfdo sync justfile                 # repo-level just targets per env and run-dir
tfdo sync github --oidc            # workflows, env secrets, IAM roles
```

After this you have:

- `tfdo.yaml` at the repo root, env layer, and run-dir layer.
- `envs/{env}/{run_dir}/` with backend, providers, and module calls.
- A `justfile` whose targets match the discovered tree.
- GitHub Actions workflows per env, with OIDC trust roles so Actions reaches state without long-lived AWS keys.

## Concepts

`tfdo` uses vocabulary that applies to any Terraform orchestrator, not just this one. The short version:

- **Run directory**: Any directory containing a `backend {}` block. One backend equals one plan/apply scope. The atomic unit `tfdo` operates on.
- **Module source**: Reusable `.tf` code with no backend. Consumed by run directories via `module {}` blocks, never planned directly.
- **Lifecycle**: `init`, `plan`, `apply`, `destroy`. `tfdo` runs them as a sequence with auto-init and retry.
- **Selectors**: Named dimensions (`env`, `team`, `app`) plus free-form `--tags key=value`. Multiple `--tags` flags AND, comma-separated values OR within a key.
- **Dependencies**: A run directory lists its parents in `tfdo.yaml`. `tfdo` builds a DAG and runs in order, passing outputs through var-files.
- **Change detection**: `tfdo run plan --changed` uses `git diff` to plan only the run directories affected by the current branch.
- **Config resolution**: CLI flag, then env var (`TFDO_*`), then nearest `tfdo.yaml`, then ancestor `tfdo.yaml`s, then user config, then default. `tfdo info` prints what won.

## Daily commands

Single run directory (`cd` into it, or pass `--work-dir`):

- **`tfdo init`**: Retries on transient registry and network errors. Injects `TF_PLUGIN_CACHE_DIR`.
- **`tfdo plan [-f vars.tfvars] [--json -o plan.json]`**: Wraps `terraform plan` with var-file and JSON helpers.
- **`tfdo apply [--auto-approve]`**: Standard apply. With `--init-mode auto`, runs `init` first when terraform reports an init-required error.
- **`tfdo destroy [--auto-approve]`**: Standard destroy.
- **`tfdo check [--fix] [--tflint]`**: ruff-style `fmt + validate` (plus optional [tflint](https://github.com/terraform-linters/tflint)). `--fix` rewrites files.
- **`tfdo info`**: Prints resolved settings, paths, and user config.

Across many run directories (`tfdo run` group):

- **`tfdo run plan --env dev`**: Plan every run directory under `envs/dev/`.
- **`tfdo run apply --tags team=infra --parallel 5`**: Tag-filtered apply, up to 5 concurrent.
- **`tfdo run plan --changed`**: Only run directories touched by `git diff` vs `HEAD`.
- **`tfdo run plan --dry-run`**: Print the wave plan without running terraform.
- **`tfdo run apply --on-failure continue`**: Keep going past a failed run directory.

Other groups:

- **`tfdo config init|show`**: Generate or print resolved `tfdo.yaml` layers.
- **`tfdo new run-dir`**: Scaffold new stacks against modules selected during `boot`.
- **`tfdo copy env`**: Copy a known-good env (e.g. `dev`) into a new env (e.g. `prod`).
- **`tfdo schema show|diff`**: Fetch provider schemas; diff between two versions or the local `dev` plugin.
- **`tfdo inspect resource-usage|hcl-paths|api-coverage`**: Walk HCL against provider schemas for coverage and gap reports.
- **`tfdo sync justfile|github`**: Regenerate repo glue when run directories change.

## Configuration

`tfdo.yaml` stacks from the git root down to each run directory. Layers higher in the tree provide defaults; lower layers override.

```yaml
# repo-root tfdo.yaml
backend:
  type: s3
  bucket: my-tf-state
  key: "envs/{env}/{run_dir}/terraform.tfstate"
  region: eu-west-1
  dynamodb_table: my-tf-lock

run_dir_discovery: "envs/{env}/{run_dir}"

tags:
  managed_by: tfdo
tags_inject: aws        # rewrite aws_* resources to carry these tags

providers:
  - name: mongodbatlas
    constraint: ">= 1.20.0"

ci:
  repo_org: EspenAlbert
  repo_name: my-atlas-infra
  oidc: true
```

Key concepts:

- **Discovery pattern**: `run_dir_discovery` is a path with named selectors. The first selector must be `{env}`. Selectors auto-populate CLI filters (`--env`, `--app`, `--team`).
- **Backend**: `s3` or `local`, defined once at the root and rendered into each run directory's `backend "s3" {}` block.
- **Layered overrides**: An env-level `tfdo.yaml` can override `binary`, `tf_version`, `tags`, or pin different provider versions per env.
- **Var-file resolution**: `var_files` and `env_var_files` resolve relative to each layer, so dev and prod can share `common.tfvars` while overriding specific knobs.
- **Hooks**: `hook_configs` runs a shell command or Python entry-point on lifecycle events (`pre_init`, `pre_plan`, `post_apply`, ...). Input and output flow through env vars and JSON files.
- **Dependencies**: `dependencies: [{ref: ../project}]` pulls outputs from another run directory as `.dep.tfvars.json` so ordering is explicit.

`tfdo config show` prints the resolved layers for the current run directory.

## How it differs from Terragrunt, Terramate, and Atmos

- **vs [Terragrunt](https://terragrunt.gruntwork.io/)**: Same wrapper idea, flat YAML instead of HCL include chains. No `.terragrunt-cache` temp dirs; tfdo runs in place. Auto-init is explicit through `--init-mode`, not magic.
- **vs [Terramate](https://terramate.io/)**: Borrows the change-detection idea via `git diff`, stays closer to the terraform CLI. `tfdo run --changed plan` instead of `terramate run -- terraform plan`. No `.tm.hcl` files, no stack UUIDs.
- **vs [Atmos](https://atmos.tools/)**: YAML config too, no component/stack abstraction. Run directories map directly to root module directories. No mandatory Spacelift integration.
- **Unique territory**: Schema diffing, resource-usage analysis, and provider breaking-change detection. None of the orchestrators above inspect provider schemas.

## Design principles

- **Wrap, never fork**: `tfdo` calls `terraform` or `tofu` (`--binary`, `TFDO_BINARY`). Any run directory still works with plain `terraform plan`.
- **One effective environment per invocation**: A single run uses one coherent set of env vars. Multi-step orchestration spawns separate invocations when credentials differ.
- **Committed Terraform preferred**: Generated `.tf` lives in git, reviewable in PRs. The `--debug` flag (and `tfdo config show`) surfaces what was generated.
- **Config simplicity over power**: `tfdo.yaml` is flat YAML with pydantic validation. No custom functions, no include chains, no expression evaluation at config-load time.

## Environment variables

All env vars use the `TFDO_` prefix and override CLI flags only when the flag is not passed.

- **`TFDO_BINARY`**: Terraform binary name or path. Default `terraform`.
- **`TFDO_TF_VERSION`**: When set, binary becomes `mise x terraform@{version} -- {binary}`.
- **`TFDO_WORK_DIR`**: Working directory for terraform commands. Default `cwd`.
- **`TFDO_INTERACTIVE`**: `auto` (detect TTY), `always`, or `never`. With `never`, prompting commands require `--auto-approve`.
- **`TFDO_INIT_MODE`**: `auto` (init on init-error), `always`, or `never`. Default `auto`.
- **`TFDO_TFLINT`**: Run tflint alongside `check`.
- **`TFDO_VERBOSE_SHELL`**: Log every successful shell completion (default is errors only).
- **`TFDO_BACKENDS_DIRS`, `TFDO_ENV_VARS_DIRS`, `TFDO_PROVIDER_HINTS_PATH`**: Override the static directories shipped with `tfdo`.
- **`CACHE_DIR`**: Override the per-user cache base; bypasses platformdirs. See [caching](docs/caching.md).

`tfdo info` prints the resolved values for the current shell.

## Development

From the repo root:

```sh
just pre-commit                    # fmt + fix + lint
just pre-push                      # lint + fmt-check + test + vulture
just test                          # tests only
just docs-serve                    # local mkdocs preview
```

Internal architecture lives in [`CLAUDE.md`](./CLAUDE.md). Public API and CLI reference live under [`docs/`](./docs/) and ship via [mkdocs-material](https://squidfunk.github.io/mkdocs-material/).

## License

[MIT](./LICENSE).
