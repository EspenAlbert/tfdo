from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from tfdo._internal.cache import provider_version_cache as _module
from tfdo._internal.cache.provider_version_cache import (
    _is_exact_version,
    resolve_provider_versions,
)
from tfdo._internal.config.config_model import ProviderConstraint
from tfdo._internal.hcl_read import LOCK_FILENAME, parse_lock_file_versions
from tfdo._internal.models import InitResult
from tfdo._internal.settings import InteractiveMode, TfDoSettings

_MODULE = _module.__name__


def _settings(tmp_path: Path) -> TfDoSettings:
    return TfDoSettings.for_testing(tmp_path, work_dir=tmp_path, interactive=InteractiveMode.NEVER)


SAMPLE_LOCK_AWS = """\
provider "registry.terraform.io/hashicorp/aws" {
  version = "5.82.0"
  constraints = ">= 5.0.0"
  hashes = ["h1:abc123"]
}
"""

SAMPLE_LOCK_ATLAS = """\
provider "registry.terraform.io/mongodb/mongodbatlas" {
  version = "1.23.0"
  hashes = ["h1:def456"]
}
"""


def test_parse_lock_file_versions(tmp_path: Path):
    lock_path = tmp_path / LOCK_FILENAME
    lock_path.write_text(SAMPLE_LOCK_AWS + SAMPLE_LOCK_ATLAS)
    versions = parse_lock_file_versions(lock_path)
    assert versions["registry.terraform.io/hashicorp/aws"] == "5.82.0"
    assert versions["registry.terraform.io/mongodb/mongodbatlas"] == "1.23.0"


def test_is_exact_version():
    assert _is_exact_version("5.82.0")
    assert _is_exact_version("1.0.0")
    assert not _is_exact_version("~> 5.0")
    assert not _is_exact_version(">= 1.0.0")
    assert not _is_exact_version("")


def test_resolve_skips_exact_versions(tmp_path: Path):
    providers = [
        ProviderConstraint(name="aws", source="hashicorp/aws", constraint="5.82.0"),
    ]
    result = resolve_provider_versions(providers, _settings(tmp_path))
    assert result == providers


def _fake_init_with_lock(lock_content: str):
    def _init(input_model):
        lock_path = input_model.settings.work_dir / LOCK_FILENAME
        lock_path.write_text(lock_content)
        return InitResult(exit_code=0, attempts_used=1)

    return _init


def test_resolve_runs_init_per_provider(tmp_path: Path):
    providers = [
        ProviderConstraint(name="aws", source="hashicorp/aws"),
        ProviderConstraint(name="mongodbatlas", source="mongodb/mongodbatlas"),
    ]
    lock_by_source = {
        "hashicorp/aws": SAMPLE_LOCK_AWS,
        "mongodb/mongodbatlas": SAMPLE_LOCK_ATLAS,
    }

    def _init(input_model):
        stub = (input_model.settings.work_dir / "versions.tf").read_text()
        for source, lock in lock_by_source.items():
            if source in stub:
                return _fake_init_with_lock(lock)(input_model)
        return InitResult(exit_code=1, attempts_used=1, stderr="unknown provider")

    with patch(f"{_MODULE}.executor") as mock_executor:
        mock_executor.init.side_effect = _init
        result = resolve_provider_versions(providers, _settings(tmp_path))

    assert mock_executor.init.call_count == 2
    assert result[0].constraint == "5.82.0"
    assert result[1].constraint == "1.23.0"


def test_resolve_cache_hit_skips_init(tmp_path: Path):
    providers = [ProviderConstraint(name="aws", source="hashicorp/aws")]
    settings = _settings(tmp_path)

    with patch(f"{_MODULE}.executor") as mock_executor:
        mock_executor.init.side_effect = _fake_init_with_lock(SAMPLE_LOCK_AWS)
        first = resolve_provider_versions(providers, settings)

    with patch(f"{_MODULE}.executor") as mock_executor:
        second = resolve_provider_versions(providers, settings)

    mock_executor.init.assert_not_called()
    assert first[0].constraint == second[0].constraint == "5.82.0"


def test_resolve_partial_cache_hit(tmp_path: Path):
    """Resolving [aws] then [aws, atlas] only inits for atlas the second time."""
    settings = _settings(tmp_path)

    with patch(f"{_MODULE}.executor") as mock_executor:
        mock_executor.init.side_effect = _fake_init_with_lock(SAMPLE_LOCK_AWS)
        resolve_provider_versions([ProviderConstraint(name="aws", source="hashicorp/aws")], settings)

    both = [
        ProviderConstraint(name="aws", source="hashicorp/aws"),
        ProviderConstraint(name="mongodbatlas", source="mongodb/mongodbatlas"),
    ]
    with patch(f"{_MODULE}.executor") as mock_executor:
        mock_executor.init.side_effect = _fake_init_with_lock(SAMPLE_LOCK_ATLAS)
        result = resolve_provider_versions(both, settings)

    mock_executor.init.assert_called_once()
    assert result[0].constraint == "5.82.0"
    assert result[1].constraint == "1.23.0"


def test_resolve_loose_constraint_gets_pinned(tmp_path: Path):
    providers = [ProviderConstraint(name="aws", source="hashicorp/aws", constraint="~> 5.0")]
    with patch(f"{_MODULE}.executor") as mock_executor:
        mock_executor.init.side_effect = _fake_init_with_lock(SAMPLE_LOCK_AWS)
        result = resolve_provider_versions(providers, _settings(tmp_path))

    assert result[0].constraint == "5.82.0"


def test_resolve_graceful_on_init_failure(tmp_path: Path):
    providers = [ProviderConstraint(name="aws", source="hashicorp/aws")]
    with patch(f"{_MODULE}.executor") as mock_executor:
        mock_executor.init.return_value = InitResult(exit_code=1, attempts_used=1, stderr="no network")
        result = resolve_provider_versions(providers, _settings(tmp_path))

    assert result[0].constraint is None
