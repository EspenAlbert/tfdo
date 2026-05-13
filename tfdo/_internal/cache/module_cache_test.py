from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from tfdo._internal.cache import module_cache as _module
from tfdo._internal.cache.module_cache import UNRESOLVED, cache_dir, lookup, populate, source_safe
from tfdo._internal.models import InitInput, InitResult
from tfdo._internal.settings import TfDoSettings

_MODULE = _module.__name__


def _settings(tmp_path: Path) -> TfDoSettings:
    return TfDoSettings.for_testing(tmp_path, work_dir=tmp_path)


def _modules_json(version: str) -> str:
    return json.dumps(
        {
            "Modules": [
                {"Key": "x", "Source": "registry.terraform.io/...", "Version": version, "Dir": ".terraform/modules/x"}
            ]
        }
    )


def test_source_safe_encodes_slashes() -> None:
    assert source_safe("hashicorp/aws/modules") == "hashicorp%2Faws%2Fmodules"


def test_cache_dir_layout(tmp_path: Path) -> None:
    result = cache_dir(tmp_path, "hashicorp/aws/modules", "1.0.0")
    assert result == tmp_path / "tf_modules" / "hashicorp%2Faws%2Fmodules" / "1.0.0"


def test_lookup_miss_and_hit(tmp_path: Path) -> None:
    assert lookup(tmp_path, "my/source", "1.0.0") is None

    hit_dir = cache_dir(tmp_path, "my/source", "1.0.0")
    hit_dir.mkdir(parents=True)
    (hit_dir / "modules.json").write_text(_modules_json("1.0.0"))
    assert lookup(tmp_path, "my/source", "1.0.0") == hit_dir


def test_populate_cache_hit_skips_terraform(tmp_path: Path) -> None:
    source, version = "my/module", "1.0.0"
    target = cache_dir(tmp_path, source, version)
    target.mkdir(parents=True)
    (target / "modules.json").write_text(_modules_json(version))

    with patch(f"{_MODULE}.executor") as mock_executor:
        result = populate(tmp_path, source, version, _settings(tmp_path))

    assert result == target
    mock_executor.init.assert_not_called()


def test_populate_pinned_version_stores_under_constraint(tmp_path: Path) -> None:
    source, version = "terraform-mongodbatlas-modules/project", "0.1.0"

    def fake_init(input_model: InitInput) -> InitResult:
        modules_dir = input_model.settings.work_dir / ".terraform" / "modules"
        modules_dir.mkdir(parents=True)
        (modules_dir / "modules.json").write_text(_modules_json(version))
        assert source in (input_model.settings.work_dir / "main.tf").read_text()
        assert version in (input_model.settings.work_dir / "main.tf").read_text()
        return InitResult(exit_code=0, attempts_used=1)

    with patch(f"{_MODULE}.executor") as mock_executor:
        mock_executor.init.side_effect = fake_init
        result = populate(tmp_path, source, version, _settings(tmp_path))

    mock_executor.init.assert_called_once()
    assert result == cache_dir(tmp_path, source, version)
    assert (result / "modules.json").is_file()


def test_populate_unresolved_stores_under_resolved_version(tmp_path: Path) -> None:
    source = "my/module"
    resolved = "2.3.1"

    def fake_init(input_model: InitInput) -> InitResult:
        content = (input_model.settings.work_dir / "main.tf").read_text()
        assert "version" not in content
        modules_dir = input_model.settings.work_dir / ".terraform" / "modules"
        modules_dir.mkdir(parents=True)
        (modules_dir / "modules.json").write_text(_modules_json(resolved))
        return InitResult(exit_code=0, attempts_used=1)

    with patch(f"{_MODULE}.executor") as mock_executor:
        mock_executor.init.side_effect = fake_init
        result = populate(tmp_path, source, UNRESOLVED, _settings(tmp_path))

    assert result == cache_dir(tmp_path, source, resolved)
    assert result.name == resolved
