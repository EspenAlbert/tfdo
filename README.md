# tfdo

A [Terraform](https://developer.hashicorp.com/terraform)/[OpenTofu](https://opentofu.org/) lifecycle CLI that adds multi-directory orchestration, retry, and CI scaffolding on top of the raw `terraform`/`tofu` binary.

`tfdo` is opinionated about the following:

- **Layout**: One repo, many run directories grouped by environment (`envs/{env}/{run_dir}/`).
- **Config**: Stackable `tfdo.yaml` layers from repo root down to each run-dir.
- **Bootstrap**: One command takes an empty folder to a CI-wired repo with S3 remote state, GitHub Actions, and OIDC trust.

Full reference docs: [espenalbert.github.io/tfdo](https://espenalbert.github.io/tfdo/).

## Why tfdo

Raw `terraform` works fine for a single directory. Once you have dev/prod splits, multiple stacks, and CI that needs to plan/apply across all of them, you end up writing the same glue every time:

- A `justfile` (or Makefile) that loops `init`/`plan`/`apply` across run-dirs.
- A `terraform init` retry loop for transient registry/network errors.
- A `tfvars`/env-var resolution scheme so dev and prod share modules without sharing secrets.
- GitHub Actions workflows per environment, with OIDC trust roles per env and per backend.

`tfdo` ships those patterns as commands. The same `tfdo plan` invocation works for a single run-dir or for every dev run-dir, depending on which subcommand you call.

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

Empty directory to a CI-wired Atlas repo:

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

## Daily commands

Single run-dir (`cd` into it first, or pass `--work-dir`):

- `tfdo init`: Retries init on transient registry/network errors. Injects `TF_PLUGIN_CACHE_DIR`.
- `tfdo plan [-f vars.tfvars] [--json -o plan.json]`: Wraps `terraform plan` with var-file and JSON helpers.
- `tfdo apply [--auto-approve]`: Standard apply; runs `init` first when `--init-mode auto` detects an init-required error.
- `tfdo destroy [--auto-approve]`: Standard destroy.
- `tfdo check [--fix] [--tflint]`: ruff-style fmt + validate (+ optional tflint). `--fix` rewrites files.
- `tfdo info`: Prints resolved settings, paths, and user config.

Across many run-dirs (`tfdo run` group):

- `tfdo run plan --env dev`: Plan every run-dir under `envs/dev/`.
- `tfdo run apply --tags team=infra --parallel 5`: Tag-filtered apply, max 5 concurrent.
- `tfdo run plan --changed`: Only run-dirs touched by `git diff` vs `HEAD`.
- `tfdo run plan --dry-run`: Print the wave plan without running terraform.
- `tfdo run apply --on-failure continue`: Keep going past a failed run-dir.

Filtering combines `{env}`, `{app}`, `{team}` selectors from your discovery pattern with free-form `--tags key=value` and `--changed`. See [`run`](https://espenalbert.github.io/tfdo/run/) for the full filter table.

Other groups:

- `tfdo config init|show`: Generate or print resolved `tfdo.yaml` layers.
- `tfdo new run-dir|env`: Scaffold new stacks or copy an env layout.
- `tfdo copy env`: Copy a known-good env (e.g. dev) into a new env (e.g. prod).
- `tfdo schema show|diff`: Fetch provider schemas; diff between two versions or `dev` plugin.
- `tfdo inspect resource-usage|hcl-paths|api-coverage`: Walk HCL against provider schemas for coverage and gap reports.
- `tfdo sync justfile|github`: Regenerate repo glue when run-dirs change.

## Configuration

`tfdo.yaml` layers from the git root down to the run-dir. Layers higher in the tree provide defaults; lower layers override.

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
tags_inject: aws        # inject into aws_* resources via HCL rewrite

providers:
  - name: mongodbatlas
    constraint: ">= 1.20.0"

ci:
  repo_org: EspenAlbert
  repo_name: my-atlas-infra
  oidc: true
```

Key concepts:

- **Discovery pattern**: `run_dir_discovery` is a path with named selectors. The first selector must be `{env}`. Selectors become CLI filters (`--env`, `--app`, `--team`).
- **Backend**: `s3` or `local`. Defined once at the root; rendered into each run-dir's `backend "s3" {}` block.
- **Layered overrides**: An env-level `tfdo.yaml` can override `binary`, `tf_version`, `tags`, or pin different provider versions per env.
- **Var-file resolution**: `var_files` and `env_var_files` resolve relative to each layer, so dev and prod can share a base `common.tfvars` while overriding specific knobs.
- **Hooks**: `hook_configs` lets you run a shell command or Python entry-point on lifecycle events (`pre_init`, `pre_plan`, `post_apply`, ...) with structured input/output via env vars.
- **Dependencies**: `dependencies: [{ref: ../project}]` pulls outputs from another run-dir as `.dep.tfvars.json` so ordering is explicit.

`tfdo config show` prints the resolved layers for the current run-dir.

## Environment variables

All env vars use the `TFDO_` prefix and override CLI flags only when the flag is not passed.

- `TFDO_BINARY`: Terraform binary name or path. Default `terraform`.
- `TFDO_TF_VERSION`: When set, binary becomes `mise x terraform@{version} -- {binary}`.
- `TFDO_WORK_DIR`: Working directory for terraform commands. Default `cwd`.
- `TFDO_INTERACTIVE`: `auto` (detect TTY), `always`, or `never`. With `never`, commands that prompt require `--auto-approve`.
- `TFDO_INIT_MODE`: `auto` (init on init-error), `always`, or `never`. Default `auto`.
- `TFDO_TFLINT`: Run [tflint](https://github.com/terraform-linters/tflint) alongside `check`.
- `TFDO_VERBOSE_SHELL`: Log every successful shell completion (default is errors only).
- `TFDO_BACKENDS_DIRS`, `TFDO_ENV_VARS_DIRS`, `TFDO_PROVIDER_HINTS_PATH`: Override the static directories shipped with `tfdo`.
- `CACHE_DIR`: Override the per-user cache base; bypasses platformdirs. See [caching](https://espenalbert.github.io/tfdo/caching/).

`tfdo info` prints the resolved values for the current shell.

## How it differs from Terragrunt and friends

- **Same idea, smaller surface**: One CLI, no DSL on top of HCL. Run-dirs stay plain Terraform; `tfdo` only writes the backend, provider, and tag blocks it owns.
- **Native CI scaffold**: `tfdo sync github --oidc` provisions the OIDC trust path end-to-end (AWS OIDC provider, per-env IAM roles, GitHub env secrets), not just the workflow file.
- **Provider-aware**: `tfdo inspect` and `tfdo schema` work against cached provider schemas, so you can answer "which resources in this repo don't expose attribute X?" without running plan.
- **Designed for solo + small-team Atlas/AWS work**: Opinionated defaults around MongoDB Atlas and AWS S3 backends. The `provider_hints.yaml` registry maps provider auth bundles (env vars to TF vars) so `check` and `inspect` validate config before you run anything.

If you need cross-cloud orchestration with locks at scale, Terragrunt or Spacelift are the wider tools. If you want a single binary that knows your repo layout and your CI in advance, `tfdo` is the smaller answer.

## Development

This repo is part of a [uv](https://docs.astral.sh/uv/) workspace. From the workspace root:

```sh
just pre-commit-tfdo               # fmt + lint + tests + pyright + vulture
just test-tfdo                     # tests only
uv run pytest code/tfdo -k <name>  # single test
```

Internal architecture is documented in [`CLAUDE.md`](./CLAUDE.md). Public API and CLI reference live under [`docs/`](./docs/) and are published via [mkdocs-material](https://squidfunk.github.io/mkdocs-material/).

## License

[MIT](./LICENSE).
