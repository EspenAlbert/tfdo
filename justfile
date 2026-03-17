# path-sync copy -n python-template

# === OK_EDIT: path-sync header ===
# Custom variables and setup
REPO_URL := "https://github.com/EspenAlbert/tfdo"


# === DO_NOT_EDIT: path-sync standard ===
pre-push: lint fmt-check test vulture
  @echo "All checks passed"

pre-commit: fmt fix lint
  @echo "Pre-commit checks passed"

lint:
  uv run ruff check .

fmt:
  uv run ruff format .

fmt-check:
  uv run ruff format --check .

fix:
  uv run ruff check --fix .

test:
  uv run pytest

build:
  uv build
# === OK_EDIT: path-sync standard ===

# === DO_NOT_EDIT: path-sync vulture ===
vulture:
  uv run vulture .
# === OK_EDIT: path-sync vulture ===

# === DO_NOT_EDIT: path-sync path-sync ===
path-sync-validate:
  uv run path-sync validate-no-changes
# === OK_EDIT: path-sync path-sync ===

# === DO_NOT_EDIT: path-sync coverage ===
cov:
  uv run pytest --cov --cov-report=html

cov-full:
  uv run pytest --cov --cov-report=html --cov-report=xml

open-cov: cov
  open htmlcov/index.html
# === OK_EDIT: path-sync coverage ===

# === DO_NOT_EDIT: path-sync typing ===
type-check:
  uv run pyright
# === OK_EDIT: path-sync typing ===

# === DO_NOT_EDIT: path-sync pkg-ext ===
pkg-pre-change *args:
  uv run --group release pkg-ext pre-change {{args}}

pkg-pre-commit *args:
  uv run --group release pkg-ext --is-bot pre-commit {{args}}

pkg-post-merge *args:
  uv run --group release pkg-ext --is-bot post-merge --push {{args}}

pkg-release-notes tag:
  uv run --group release pkg-ext release-notes --tag {{tag}}
# === OK_EDIT: path-sync pkg-ext ===

# === DO_NOT_EDIT: path-sync docs ===
docs-build:
  uv run scripts/fix_source_links.py {{REPO_URL}}
  uv run --group docs mkdocs build --strict

docs-serve:
  uv run scripts/fix_source_links.py {{REPO_URL}}
  uv run --group docs mkdocs serve
# === OK_EDIT: path-sync docs ===

# Custom recipes below
